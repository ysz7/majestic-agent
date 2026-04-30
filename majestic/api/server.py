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
        if path == "/api/settings":
            return self._json(d.handle_get_settings())
        if path == "/api/memory":
            return self._json(d.handle_get_memory_md())
        if path == "/api/skills":
            return self._json(d.handle_get_skills())
        m = _match(path, "/api/skills/", "")
        if m:
            from urllib.parse import unquote
            return self._json(d.handle_get_skill_detail(unquote(m)))
        if path == "/api/tables":
            return self._json(d.handle_get_tables())
        if path == "/api/monitoring":
            return self._json(d.handle_get_monitoring())
        if path == "/api/tokens/stats":
            return self._json(d.handle_token_stats())
        if path == "/api/ollama/models":
            return self._json(d.handle_get_ollama_models())
        # /api/tables/:name/rows
        trows = _match(path, "/api/tables/", "/rows")
        if trows:
            return self._json(d.handle_get_rows(trows))
        if path in ("/api/sessions", "/sessions"):
            return self._json(d.handle_get_sessions())
        m2 = _match(path, "/api/sessions/", "/messages")
        if m2:
            return self._json(d.handle_get_messages(m2))
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
        if path == "/api/settings":
            return self._json(d.handle_save_settings(body))
        if path == "/api/memory":
            return self._json(d.handle_save_memory_md(body))
        if path == "/api/skills":
            return self._json(d.handle_create_skill(body))
        if path == "/api/sessions":
            return self._json(d.handle_create_session(body))
        if path in ("/api/chat", "/chat"):
            return self._handle_chat_sse(body)
        if path == "/api/tables":
            return self._json(d.handle_create_table(body))
        # /api/tables/:name/rows
        trows_post = _match(path, "/api/tables/", "/rows")
        if trows_post:
            return self._json(d.handle_add_row(trows_post, body))
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
        if path == "/api/settings":
            return self._json(d.handle_save_settings(body))
        return self._json({"error": "not found"}, 404)

    def do_PUT(self) -> None:
        if not _check_auth(self):
            return self._unauthorized()
        body = self._read_body()
        if body is None:
            return
        path = self.path.split("?")[0]
        from majestic.api import dashboard as d
        # /api/tables/:name/rows/:id
        seg = _split3(path, "/api/tables/", "/rows/")
        if seg:
            return self._json(d.handle_update_row(seg[0], seg[1], body))
        return self._json({"error": "not found"}, 404)

    def do_DELETE(self) -> None:
        if not _check_auth(self):
            return self._unauthorized()
        path = self.path.split("?")[0]
        from majestic.api import dashboard as d
        sid = _match(path, "/api/sessions/", "")
        if sid:
            return self._json(d.handle_delete_session(sid))
        skill = _match(path, "/api/skills/", "")
        if skill:
            from urllib.parse import unquote
            return self._json(d.handle_delete_skill(unquote(skill)))
        # /api/tables/:name/rows/:id  (before /api/tables/:name)
        trow = _split3(path, "/api/tables/", "/rows/")
        if trow:
            return self._json(d.handle_delete_row(trow[0], trow[1]))
        tname = _match(path, "/api/tables/", "")
        if tname:
            return self._json(d.handle_delete_table(tname))
        sched = _match(path, "/api/schedules/", "")
        if sched:
            return self._json(d.handle_delete_schedule(sched))
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

        # Create session lazily if none provided
        if not session_id:
            try:
                from majestic.db.state import StateDB
                from majestic import config as _cfg
                label = f"{_cfg.get('llm.provider','')}/{_cfg.get('llm.model','')}"
                session_id = StateDB().create_session(source="dashboard", model=label)
                self._sse_json({"type": "session_id", "data": session_id})
            except Exception:
                pass

        try:
            from majestic.agent.loop import AgentLoop

            def _on_tool(name: str, args: dict) -> None:
                self._sse_json({"type": "tool_call", "data": {"name": name, "args": args}})

            loop = AgentLoop()
            result = loop.run(message, session_id=session_id, history=[], on_tool_call=_on_tool)
            answer = result.get("answer", "")
            for chunk in _split_chunks(answer, 80):
                self._sse_json({"type": "text", "data": chunk})
        except Exception as e:
            self._sse_json({"type": "error", "data": str(e)})

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
            self.wfile.write(f"data: {data}\n\n".encode())
            self.wfile.flush()
        except Exception:
            pass

    def _sse_json(self, obj: Any) -> None:
        self._sse(json.dumps(obj, ensure_ascii=False))

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


def _split3(path: str, prefix: str, mid: str) -> tuple[str, str] | None:
    """Extract (part1, part2) from paths like /prefix/<p1>/mid/<p2>."""
    if not path.startswith(prefix):
        return None
    rest = path[len(prefix):]
    if mid not in rest:
        return None
    idx = rest.index(mid)
    p1 = rest[:idx]
    p2 = rest[idx + len(mid):]
    if p1 and p2:
        return (p1, p2)
    return None
