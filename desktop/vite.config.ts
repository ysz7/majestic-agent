import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

// Agent port from env (matches persona.yaml port field)
const AGENT_PORT = process.env.VITE_AGENT_PORT ?? "17000";

// https://vitejs.dev/config/
export default defineConfig(async () => ({
  plugins: [react()],

  resolve: {
    alias: {
      "@app":      resolve(__dirname, "src/app"),
      "@pages":    resolve(__dirname, "src/pages"),
      "@widgets":  resolve(__dirname, "src/widgets"),
      "@features": resolve(__dirname, "src/features"),
      "@entities": resolve(__dirname, "src/entities"),
      "@shared":   resolve(__dirname, "src/shared"),
      "@store":    resolve(__dirname, "src/store"),
    },
  },

  // Vite dev server — proxy API + WebSocket to the running agent
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: `http://localhost:${AGENT_PORT}`,
        changeOrigin: true,
      },
      // Direct agent endpoints (not under /api)
      "/task": {
        target: `http://localhost:${AGENT_PORT}`,
        changeOrigin: true,
      },
      "/status": {
        target: `http://localhost:${AGENT_PORT}`,
        changeOrigin: true,
      },
      "/message": {
        target: `http://localhost:${AGENT_PORT}`,
        changeOrigin: true,
      },
      "/ws": {
        target: `ws://localhost:${AGENT_PORT}`,
        ws: true,
        changeOrigin: true,
        configure: (proxy) => {
          // Suppress ECONNABORTED noise from reconnect cycles
          proxy.on("error", () => {});
        },
      },
    },
  },

  // Tauri expects a fixed port in dev
  clearScreen: false,
}));
