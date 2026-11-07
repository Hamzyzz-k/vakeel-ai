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
