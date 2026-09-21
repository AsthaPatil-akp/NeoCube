import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/auth": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/users": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/categories": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/requirements": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/offerings": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/documents": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/supplier-documents": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/notifications": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        bypass(req) {
          if (req.headers.accept?.includes("text/html")) {
            return "/index.html";
          }
        },
      },
      "/admin": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        bypass(req) {
          if (req.headers.accept?.includes("text/html")) {
            return "/index.html";
          }
        },
      },
      "/rfqs": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        bypass(req) {
          if (req.headers.accept?.includes("text/html")) {
            return "/index.html";
          }
        },
      },
      "/suppliers": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        bypass(req) {
          if (req.headers.accept?.includes("text/html")) {
            return "/index.html";
          }
        },
      },
      "/health": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
