import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";

export default defineConfig(({ command, mode }) => {
  // Always resolve env files relative to this config file (frontend/),
  // so running via npm --prefix / workspace root still works.
  const configDir = dirname(fileURLToPath(import.meta.url));
  const env = loadEnv(mode, configDir, "VITE_");

  const backendUrlFromEnv = env.VITE_BACKEND_URL;
  const backendHostFromEnv = env.VITE_BACKEND_HOST;
  const backendPortFromEnv = env.VITE_BACKEND_PORT || "8080";
  const backendProtoFromEnv = env.VITE_BACKEND_PROTO || "http";

  const backendTarget =
    backendUrlFromEnv ||
    (backendHostFromEnv
      ? `${backendProtoFromEnv}://${backendHostFromEnv}:${backendPortFromEnv}`
      : "http://localhost:8080");

  return {
    plugins: [react()],
    envDir: configDir,
    // Never bake dev API keys into the production bundle (e.g. CI with VITE_API_KEY set).
    // Dev-only usage still reads real values from .env.local when `vite` runs (mode development).
    define:
      mode === "production"
        ? { "import.meta.env.VITE_API_KEY": JSON.stringify("") }
        : undefined,
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
      watch: {
        // Ensure CSS and other src files trigger HMR (don't ignore our source)
        ignored: ["**/node_modules/**", "**/.git/**"],
      },
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
