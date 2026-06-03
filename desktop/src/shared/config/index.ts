// Agent API base URL — reads port from ?agentPort= query param or defaults to 8000.
// In Tauri dev mode the Vite proxy forwards /api and /ws automatically.
// In production the Tauri WebView talks directly to the agent server.

function resolveBase(): string {
  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    const port = params.get("agentPort") ?? "8000";
    // In Tauri production (tauri://localhost) hit agent directly
    if (window.location.protocol === "tauri:") {
      return `http://localhost:${port}`;
    }
  }
  // In Vite dev mode the proxy handles /api/* and /ws
  return "";
}

export const API_BASE = resolveBase();
export const WS_BASE = API_BASE.replace(/^http/, "ws");
