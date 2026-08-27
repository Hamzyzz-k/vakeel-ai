import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Local development can target a second backend port without rewriting the
// app. Production still uses VITE_API_BASE_URL from src/lib/api.js.
const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  envDir: "..",
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
});
