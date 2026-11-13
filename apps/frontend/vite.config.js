import { defineConfig } from "vite";

const target = process.env.BACKEND_URL || "http://127.0.0.1:8000";
export default defineConfig({
  server: {
    port: Number(process.env.FRONTEND_PORT || 8080),
    strictPort: true,
    proxy: {
      "/api": { target, timeout: 360000, proxyTimeout: 360000 },
    },
  },
});
