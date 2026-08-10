import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Local-only for now: proxy /api straight to the FastAPI backend on 8000.
// If CLOUD mode is ever wired up, this becomes an env-driven base URL --
// see backend/app/config.py for the mirrored switch.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
