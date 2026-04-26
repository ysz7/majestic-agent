"""
HTTP REST API for Majestic — stdlib only, no extra deps.

Endpoints:
  GET  /health              → {"status": "ok", "version": "..."}
  GET  /sessions            → [{"id":..., "created_at":..., "source":...}]
  POST /chat                → {"message": "...", "session_id"?: "..."}
                            ← {"answer": "...", "tools_used": [...], "cost_usd": 0.0, "elapsed_s": 1.2}
  POST /run                 → {"prompt": "...", "session_id"?: "..."}  (fire-and-forget, returns 202)

Auth: if config api.key is set, all requests must include header X-API-Key: <key>.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

PORT = 8080
_started = False


def start(port: int = PORT) -> None:
    """Start the API server on a daemon thread. Safe to call multiple times."""
    global _started
    if _started:
        return
    _started = True
    server = HTTPServer(("0.0.0.0", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True, name="api-server").start()
    print(f"  API server listening on http://0.0.0.0:{port}", flush=True)


def _api_key() -> str:
    try:
        from majestic import config as _cfg
        return _cfg.get("api.key", "") or ""
    except Exception:
        return ""


def _check_auth(handler: "BaseHTTPRequestHandler") -> bool:
    key = _api_key()
    if not key:
        return True
    return handler.headers.get("X-API-Key", "") == key


def _version() -> str:
    try:
        from importlib.metadata import version
        return version("majestic-agent")
    except Exception:
        return "0.1.0-dev"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_) -> None:
        pass

    # ── Routing ───────────────────────────────────────────────────────────────

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json({"status": "ok", "version": _version()})
        elif self.path == "/sessions":
            if not _check_auth(self):
                return self._unauthorized()
            self._handle_sessions()
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        if not _check_auth(self):
            return self._unauthorized()
        body = self._read_body()
        if body is None:
            return
        if self.path == "/chat":
            self._handle_chat(body)
        elif self.path == "/run":
            self._handle_run(body)
        else:
            self._json({"error": "not found"}, 404)

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _handle_chat(self, body: dict) -> None:
        message = body.get("message", "").strip()
        if not message:
            return self._json({"error": "message required"}, 400)

        session_id = body.get("session_id") or None
        tools_used: list[str] = []
        start_t = time.time()

        try:
            from majestic import config as _cfg
            from majestic.agent.loop import AgentLoop
            from majestic.token_tracker import get_stats

            cost_before = get_stats().get("cost_usd", 0.0)

            def _on_tool(name: str, _args: dict) -> None:
                tools_used.append(name)

            loop = AgentLoop()
            result = loop.run(message, session_id=session_id, history=[], on_tool_call=_on_tool)
            answer = result.get("answer", "")
            cost = max(0.0, get_stats().get("cost_usd", 0.0) - cost_before)
        except Exception as e:
            return self._json({"error": str(e)}, 500)

        self._json({
            "answer":     answer,
            "tools_used": tools_used,
            "cost_usd":   round(cost, 6),
            "elapsed_s":  round(time.time() - start_t, 2),
        })

    def _handle_run(self, body: dict) -> None:
        prompt = body.get("prompt", "").strip()
        if not prompt:
            return self._json({"error": "prompt required"}, 400)
        session_id = body.get("session_id") or None

        def _bg() -> None:
            try:
                from majestic.agent.loop import AgentLoop
                AgentLoop().run(prompt, session_id=session_id, history=[])
            except Exception:
                pass

        threading.Thread(target=_bg, daemon=True).start()
        self._json({"status": "accepted"}, 202)

    def _handle_sessions(self) -> None:
        try:
            from majestic.db.state import StateDB
            rows = StateDB().get_recent_sessions(limit=20)
            self._json(rows)
        except Exception as e:
            self._json({"error": str(e)}, 500)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _read_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            self._json({"error": "empty body"}, 400)
            return None
        try:
            data = json.loads(self.rfile.read(length).decode())
        except Exception:
            self._json({"error": "invalid JSON"}, 400)
            return None
        if not isinstance(data, dict):
            self._json({"error": "expected JSON object"}, 400)
            return None
        return data

    def _json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _unauthorized(self) -> None:
        self._json({"error": "unauthorized"}, 401)
