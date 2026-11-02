import path from "node:path";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

import { assertProductionApiUrl } from "./src/api/releaseApiUrl";

function requireProductionHttpsApiUrl(): Plugin {
  return {
    name: "require-production-https-api-url",
    configResolved(config) {
      if (config.command !== "build" || config.mode !== "production") return;
      assertProductionApiUrl(process.env.VITE_API_URL);
    },
  };
}

// Web client for Recall. Talks to the existing FastAPI over HTTP + SSE.
// The API URL is configured per-environment via VITE_API_URL (see .env.example).
export default defineConfig({
  plugins: [react(), requireProductionHttpsApiUrl()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
  },
});
