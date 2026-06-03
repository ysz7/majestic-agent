import { WS_BASE } from "@shared/config";
import type { WsEvent } from "@shared/api/types";

type Listener = (event: WsEvent) => void;

class WsClient {
  private ws: WebSocket | null = null;
  private listeners = new Set<Listener>();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private token = "";

  connect(token: string): void {
    this.token = token;
    this._open();
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }

  on(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  send(msg: object): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  ping(): void {
    this.send({ type: "ping" });
  }

  private _open(): void {
    const url = `${WS_BASE}/ws?token=${encodeURIComponent(this.token)}`;
    this.ws = new WebSocket(url);

    this.ws.onmessage = (e) => {
      try {
        const event: WsEvent = JSON.parse(e.data as string);
        this.listeners.forEach((l) => l(event));
      } catch {
        // ignore malformed frames
      }
    };

    this.ws.onclose = () => {
      this.reconnectTimer = setTimeout(() => this._open(), 3000);
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }
}

// Singleton — one WS connection per app instance
export const wsClient = new WsClient();
