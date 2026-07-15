import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, /api and health routes proxy to the FastAPI backend on :8000,
// so the SPA and API share an origin and SSO/cookies behave correctly.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/healthz": "http://localhost:8000",
      "/readyz": "http://localhost:8000",
    },
  },
});
