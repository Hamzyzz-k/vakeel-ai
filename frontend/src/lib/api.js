const baseUrl = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

export function apiUrl(path) {
  return `${baseUrl}${path}`;
}

export class RequestTimeoutError extends Error {}

// A plain fetch has no deadline, so a stalled request left the "working"
// status spinning forever. Abort after `timeoutMs` and say so plainly.
export async function fetchWithTimeout(path, options = {}, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(apiUrl(path), { ...options, signal: controller.signal });
  } catch (err) {
    if (err.name === "AbortError") {
      throw new RequestTimeoutError(`No response after ${Math.round(timeoutMs / 1000)}s`);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

// POSTs to the streaming chat route and calls onStage for each real
// pipeline stage, resolving with the final /chat-shaped answer. EventSource
// can't send a POST body, so this reads the event stream by hand. If the
// stream can't be opened (an older backend without the route, or a proxy
// that strips it), it falls back to the plain /chat request.
export async function streamChat(body, onStage, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const request = {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: controller.signal,
  };
  try {
    let res = await fetch(apiUrl("/api/v1/chat/stream"), request);
    if (res.status === 404 || res.status === 405) {
      res = await fetch(apiUrl("/api/v1/chat"), request);
      if (!res.ok) throw await responseError(res);
      return await res.json();
    }
    if (!res.ok) throw await responseError(res);
    if (!res.body) throw new Error("The server returned no response body");

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let answer = null;
    // Read to the end even after `final`: the server closes right after it,
    // and stopping early leaves the request reported as aborted.
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const event = block.match(/^event: (.*)$/m)?.[1];
        const data = JSON.parse(block.match(/^data: (.*)$/m)?.[1] || "{}");
        if (event === "stage") onStage(data);
        else if (event === "final") answer = data;
        else if (event === "error") throw new Error(data.detail || "The answer could not be generated");
      }
    }
    if (answer) return answer;
    throw new Error("The connection closed before the answer arrived");
  } catch (err) {
    if (err.name === "AbortError") {
      throw new RequestTimeoutError(`No response after ${Math.round(timeoutMs / 1000)}s`);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

async function responseError(res) {
  // Limit messages (429) carry a readable detail; show it, not the code.
  const body = await res.json().catch(() => ({}));
  return new Error(body.detail || `Server responded ${res.status}`);
}
