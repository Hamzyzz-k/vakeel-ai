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
  const post = (path) => withSession((extra) => fetch(apiUrl(path), {
    ...request,
    headers: { ...request.headers, ...extra },
  }));
  try {
    let res = await post("/api/v1/chat/stream");
    if (res.status === 404 || res.status === 405) {
      res = await post("/api/v1/chat");
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

// Cloudflare Turnstile bot check. Off unless VITE_TURNSTILE_SITE_KEY is set
// at build time (the backend is off too until it has the secret key). When
// on, one passed check buys a session token that chat and upload send in
// X-Session-Token; a 401 means it expired, so the check runs again.
const turnstileSiteKey = import.meta.env.VITE_TURNSTILE_SITE_KEY || "";
const TURNSTILE_SCRIPT = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
let session = null;
let turnstileLoader = null;

function loadTurnstile() {
  if (window.turnstile) return Promise.resolve(window.turnstile);
  if (!turnstileLoader) {
    turnstileLoader = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = TURNSTILE_SCRIPT;
      script.async = true;
      script.onload = () => resolve(window.turnstile);
      script.onerror = () => {
        turnstileLoader = null;
        reject(new Error("The verification check couldn't load. Check your connection and try again."));
      };
      document.head.appendChild(script);
    });
  }
  return turnstileLoader;
}

// Renders into #turnstile-slot. "interaction-only" keeps the widget hidden
// unless Cloudflare needs the visitor to click, which is rare.
async function solveTurnstile() {
  const turnstile = await loadTurnstile();
  const slot = document.getElementById("turnstile-slot");
  if (!slot) throw new Error("The verification check couldn't start.");
  return new Promise((resolve, reject) => {
    let widgetId = null;
    const finish = (settle) => {
      if (widgetId !== null) setTimeout(() => turnstile.remove(widgetId), 0);
      settle();
    };
    widgetId = turnstile.render(slot, {
      sitekey: turnstileSiteKey,
      appearance: "interaction-only",
      callback: (token) => finish(() => resolve(token)),
      "error-callback": () => finish(() => reject(new Error("Verification failed. Please try again."))),
      "timeout-callback": () => finish(() => reject(new Error("Verification timed out. Please try again."))),
    });
  });
}

async function ensureSession(force = false) {
  if (!turnstileSiteKey) return null;
  if (!force && session && session.expiresAt > Date.now() + 30000) return session.token;
  const turnstileToken = await solveTurnstile();
  const res = await fetch(apiUrl("/api/v1/session"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ turnstile_token: turnstileToken }),
  });
  if (!res.ok) throw await responseError(res);
  const data = await res.json();
  session = data.required ? { token: data.session, expiresAt: Date.now() + data.expires_in * 1000 } : null;
  return session?.token ?? null;
}

// send(extraHeaders) performs the request; retried once with a fresh
// session if the server says the current one is missing or expired.
async function withSession(send) {
  const token = await ensureSession();
  const res = await send(token ? { "X-Session-Token": token } : {});
  if (res.status !== 401 || !turnstileSiteKey) return res;
  session = null;
  return send({ "X-Session-Token": await ensureSession(true) });
}

export function fetchWithSession(path, options = {}, timeoutMs) {
  return withSession((extra) => fetchWithTimeout(path, { ...options, headers: { ...(options.headers || {}), ...extra } }, timeoutMs));
}
