import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ command }) => {
  const backendTarget = process.env.VITE_BACKEND_URL || "http://localhost:8080";

  return {
    plugins: [react()],
    base: command === "build" ? "/static/ui/" : "/",
    build: {
      outDir: "../src/static/ui",
      emptyOutDir: true,
      sourcemap: false,
    },
    server: {
      host: true,
      port: 5173,
      strictPort: true,
      proxy: {
        "/api": {
          target: backendTarget,
          changeOrigin: true,
          ws: true,
        },
        "/scalar": {
          target: backendTarget,
          changeOrigin: true,
        },
        "/openapi.json": {
          target: backendTarget,
          changeOrigin: true,
        },
      },
    },
  };
});
