"""
HTTP REST API for Majestic — stdlib only, no extra deps.

GET  /health
GET  /api/setup/status
POST /api/setup
GET  /api/config
PATCH /api/config
GET  /api/memory
DELETE /api/memory/<key>
GET  /api/skills
GET  /api/tables
POST /api/tables
GET  /api/tokens/stats
GET  /api/sessions
POST /api/sessions
GET  /api/sessions/<id>/messages
POST /api/chat  (SSE stream)
GET  /*         static SPA fallback

Auth: if config api.key is set, all requests must include X-API-Key header.
Dashboard without password: only accepts connections from localhost.
"""
from __future__ import annotations

import json
import mimetypes
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

PORT = 8080
_started = False
_STATIC = Path(__file__).parent / "static"
_START_TIME = time.time()


def start(port: int = PORT) -> None:
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


def _check_auth(handler: BaseHTTPRequestHandler) -> bool:
    key = _api_key()
    if not key:
        # Without a key, only allow localhost
        host = handler.client_address[0]
        return host in ("127.0.0.1", "::1", "localhost")
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

    # ── CORS (dev support) ────────────────────────────────────────────────────

    def _cors(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    # ── Routing ───────────────────────────────────────────────────────────────

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        from majestic.api import dashboard as d
        if path == "/health":
            return self._json({"status": "ok", "version": _version(), "uptime": round(time.time() - _START_TIME)})
        if not _check_auth(self):
            return self._unauthorized()
        if path == "/api/setup/status":
            return self._json(d.handle_setup_status())
        if path == "/api/config":
            return self._json(d.handle_get_config())
        if path == "/api/memory":
            return self._json(d.handle_get_memory())
        if path == "/api/skills":
            return self._json(d.handle_get_skills())
        if path == "/api/tables":
            return self._json(d.handle_get_tables())
        if path == "/api/tokens/stats":
            return self._json(d.handle_token_stats())
        if path in ("/api/sessions", "/sessions"):
            return self._json(d.handle_get_sessions())
        m = _match(path, "/api/sessions/", "/messages")
        if m:
            return self._json(d.handle_get_messages(m))
        # Static SPA fallback
        return self._serve_static(path)

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        from majestic.api import dashboard as d
        # Setup doesn't require auth (first-run)
        body = self._read_body()
        if body is None:
            return
        if path == "/api/setup":
            return self._json(d.handle_setup(body))
        if not _check_auth(self):
            return self._unauthorized()
        if path == "/api/sessions":
            return self._json(d.handle_create_session(body))
        if path in ("/api/chat", "/chat"):
            return self._handle_chat_sse(body)
        if path == "/api/tables":
            return self._json(d.handle_create_table(body))
        if path == "/run":
            return self._handle_run(body)
        return self._json({"error": "not found"}, 404)

    def do_PATCH(self) -> None:
        if not _check_auth(self):
            return self._unauthorized()
        body = self._read_body()
        if body is None:
            return
        path = self.path.split("?")[0]
        from majestic.api import dashboard as d
        if path == "/api/config":
            return self._json(d.handle_patch_config(body))
        return self._json({"error": "not found"}, 404)

    def do_DELETE(self) -> None:
        if not _check_auth(self):
            return self._unauthorized()
        path = self.path.split("?")[0]
        from majestic.api import dashboard as d
        m = _match(path, "/api/memory/", "")
        if m:
            from urllib.parse import unquote
            return self._json(d.handle_delete_memory(unquote(m)))
        return self._json({"error": "not found"}, 404)

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _handle_chat_sse(self, body: dict) -> None:
        message = body.get("message", "").strip()
        if not message:
            return self._json({"error": "message required"}, 400)
        session_id = body.get("session_id") or None

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self._cors()
        self.end_headers()

        try:
            from majestic.agent.loop import AgentLoop

            buf: list[str] = []

            def _on_token(tok: str) -> None:
                buf.append(tok)
                self._sse(tok)

            loop = AgentLoop()
            result = loop.run(message, session_id=session_id, history=[], on_token=_on_token)
            # If no streaming happened (non-streaming provider), send full answer
            if not buf:
                answer = result.get("answer", "")
                for chunk in _split_chunks(answer, 80):
                    self._sse(chunk)
        except Exception as e:
            self._sse(f"\n[Error: {e}]")

        self._sse("[DONE]")

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

    def _serve_static(self, path: str) -> None:
        if not _STATIC.exists():
            return self._json({"error": "not found"}, 404)
        # Normalise path
        rel = path.lstrip("/") or "index.html"
        candidate = (_STATIC / rel).resolve()
        # Security: ensure path stays inside _STATIC
        try:
            candidate.relative_to(_STATIC.resolve())
        except ValueError:
            return self._json({"error": "forbidden"}, 403)
        if not candidate.exists() or not candidate.is_file():
            # SPA fallback
            candidate = _STATIC / "index.html"
        if not candidate.exists():
            return self._json({"error": "not found"}, 404)
        content = candidate.read_bytes()
        mime, _ = mimetypes.guess_type(str(candidate))
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self._cors()
        self.end_headers()
        self.wfile.write(content)

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
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _sse(self, data: str) -> None:
        try:
            line = f"data: {data}\n\n".encode()
            self.wfile.write(line)
            self.wfile.flush()
        except Exception:
            pass

    def _unauthorized(self) -> None:
        self._json({"error": "unauthorized"}, 401)


def _match(path: str, prefix: str, suffix: str) -> str | None:
    if path.startswith(prefix) and path.endswith(suffix):
        inner = path[len(prefix):]
        if suffix:
            inner = inner[: -len(suffix)]
        if inner:
            return inner
    return None


def _split_chunks(text: str, size: int) -> list[str]:
    return [text[i: i + size] for i in range(0, len(text), size)]
