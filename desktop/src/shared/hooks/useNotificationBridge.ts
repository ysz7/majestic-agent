import { useEffect } from "react";
import { wsClient } from "@shared/ws/client";
import { showNativeNotification } from "@shared/lib/tauri";

// Listens to WS events and fires native notifications for important events.
export function useNotificationBridge(): void {
  useEffect(() => {
    return wsClient.on((e) => {
      switch (e.type) {
        case "done":
          showNativeNotification(
            "Task completed",
            `Tokens: ${e.tokens.toLocaleString()} · $${e.cost.toFixed(4)}`,
          );
          break;
        case "error":
          showNativeNotification("Agent error", e.message.slice(0, 120));
          break;
        case "hitl":
          showNativeNotification(
            "Awaiting confirmation",
            `Tool: ${e.tool} — switch to Majestic to review`,
          );
          break;
      }
    });
  }, []);
}
