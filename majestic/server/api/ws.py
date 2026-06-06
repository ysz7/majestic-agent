"""Desktop API — WebSocket endpoint for live streaming and step events.

Connection flow:
  1. Client connects to /ws?token=<agent_token>
  2. Server sends {"type": "connected", "agent": "<name>"}
  3. Client sends {"type": "ping"} → server replies {"type": "pong"}
  4. When agent processes a task, runtime emits events into _event_bus;
     all connected clients receive them.

Event types emitted by the server:
  {"type": "token",   "content": "..."}          streaming token
  {"type": "step",    "step": "REASON|TOOL|OBSERVE", "content": "..."}
  {"type": "hitl",    "task_id": "...", "tool": "...", "args": {...}}
  {"type": "done",    "task_id": "...", "tokens": N, "cost": 0.0}
  {"type": "error",   "message": "..."}
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["ws"])

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# Global event bus: all active WS connections subscribe to this queue set.
# The AgentRuntime (or a bridge) pushes events here via emit_event().
_subscribers: set[asyncio.Queue[dict]] = set()


def emit_event(event: dict[str, Any]) -> None:
    """Push an event to all connected WebSocket clients (call from runtime/channel)."""
    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


def _load_token() -> str:
    path = _PROJECT_ROOT / "data" / "agent_token"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str | None = None) -> None:
    expected = _load_token()
    if expected and token != expected:
        await ws.close(code=4001)
        return

    await ws.accept()

    # Determine agent name from any running settings context
    agent_name = "majestic"
    try:
        from majestic.cli.registry_db import load_registry

        reg = load_registry()
        if reg:
            agent_name = next(iter(reg.values())).get("agent_name", "majestic")
    except Exception:
        pass

    await ws.send_text(json.dumps({"type": "connected", "agent": agent_name}))

    queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=256)
    _subscribers.add(queue)

    async def _sender() -> None:
        while True:
            event = await queue.get()
            try:
                await ws.send_text(json.dumps(event))
            except Exception:
                break

    sender_task = asyncio.create_task(_sender())

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if msg.get("type") == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    finally:
        sender_task.cancel()
        _subscribers.discard(queue)
