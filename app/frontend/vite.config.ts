import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api to a backend. By default the local FastAPI on :8000;
// set VITE_API_TARGET (+ optional VITE_API_TOKEN) to point at a deployed app so
// you can iterate on the UI without running the backend (or Lakebase) locally.
const target = process.env.VITE_API_TARGET || "http://localhost:8000";
const token = process.env.VITE_API_TOKEN;

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target,
        changeOrigin: true,
        secure: true,
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
