const baseUrl = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

export function apiUrl(path) {
  return `${baseUrl}${path}`;
}
