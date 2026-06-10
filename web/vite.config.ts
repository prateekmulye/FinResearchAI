import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// The FastAPI backend (uvicorn) listens on 7860 in dev.
const BACKEND = "http://localhost:7860";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
    // recharts pulls react-smooth + a nested react-is@18; without deduping,
    // Vite's dep optimizer pre-bundles a SECOND React copy, so recharts' hooks
    // (useRef) resolve to null and the chart crashes the route boundary. Pin a
    // single React instance. (Caught only by live validation — mocked tests
    // stub recharts away.)
    dedupe: ["react", "react-dom"],
  },
  // Pre-bundle recharts and its React-touching transitive deps against the app's
  // single React, so the dev optimizer never spins up a duplicate copy.
  optimizeDeps: {
    include: ["recharts", "react-smooth", "react-is"],
  },
  server: {
    port: 5173,
    proxy: {
      // SSE: do NOT buffer — proxy must stream chunks through for live tokens.
      "/api": { target: BACKEND, changeOrigin: true },
      "/healthz": { target: BACKEND, changeOrigin: true },
    },
  },
  build: {
    target: "es2022",
    sourcemap: true,
  },
});
