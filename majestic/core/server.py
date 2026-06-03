"""
majestic.core.server
~~~~~~~~~~~~~~~~~~~~
FastAPI HTTP server for background agent mode.

Exposes three endpoints:
  POST /task    — submit a task to the agent's channel queue
  GET  /status  — health check; returns agent name and port
  POST /message — alias for /task (future: Telegram/webhook)
"""

from __future__ import annotations

import secrets
import time
import uuid
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ---------------------------------------------------------------------------
# Rate limiting — simple sliding-window counter per IP
# ---------------------------------------------------------------------------

_RATE_LIMIT = 10        # max requests per window
_RATE_WINDOW = 1.0      # window size in seconds
_rate_counts: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(ip: str) -> bool:
    now = time.monotonic()
    window = _rate_counts[ip]
    _rate_counts[ip] = [t for t in window if now - t < _RATE_WINDOW]
    if len(_rate_counts[ip]) >= _RATE_LIMIT:
        return False
    _rate_counts[ip].append(now)
    return True


# ---------------------------------------------------------------------------
# Observability — lightweight Prometheus-format metrics
# ---------------------------------------------------------------------------

_metrics: dict[str, int | float] = {
    "tasks_accepted": 0,
    "tasks_rejected_rate": 0,
    "tasks_rejected_full": 0,
}


def _prometheus_text(channel) -> str:
    lines = [
        "# HELP majestic_tasks_accepted_total Tasks accepted into the queue",
        "# TYPE majestic_tasks_accepted_total counter",
        f"majestic_tasks_accepted_total {_metrics['tasks_accepted']}",
        "# HELP majestic_tasks_rejected_total Tasks rejected (rate limit or queue full)",
        "# TYPE majestic_tasks_rejected_total counter",
        f'majestic_tasks_rejected_total{{reason="rate_limit"}} {_metrics["tasks_rejected_rate"]}',
        f'majestic_tasks_rejected_total{{reason="queue_full"}} {_metrics["tasks_rejected_full"]}',
        "# HELP majestic_queue_size Current number of tasks waiting in queue",
        "# TYPE majestic_queue_size gauge",
        f"majestic_queue_size {channel.queue_size()}",
    ]
    return "\n".join(lines) + "\n"


def _token_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "data" / "agent_token"


def _load_or_create_token() -> str:
    path = _token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    token = secrets.token_hex(32)
    path.write_text(token, encoding="utf-8")
    return token


_AGENT_TOKEN = _load_or_create_token()


def create_app(channel, settings) -> FastAPI:
    """Build and return the FastAPI application.

    Args:
        channel: A channel instance with an async ``enqueue(task: dict)`` method.
        settings: A Settings object exposing ``agent_name`` and ``agent_port``.

    Returns:
        Configured FastAPI application (not yet running).
    """
    app = FastAPI(title="Majestic Agent Server")

    # Allow Tauri WebView and Vite dev server to call the API
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["tauri://localhost", "https://tauri.localhost", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Desktop API — profiles, agents, memory, skills, workspace, budget + WebSocket
    from majestic.core.api import create_desktop_router
    from majestic.core.api.ws import router as ws_router

    app.include_router(create_desktop_router())
    app.include_router(ws_router)

    async def _check_token(x_agent_token: str | None = Header(default=None)) -> None:
        if x_agent_token != _AGENT_TOKEN:
            raise HTTPException(status_code=401, detail="Unauthorized")

    @app.post("/task", dependencies=[__import__("fastapi").Depends(_check_token)])
    async def receive_task(request: Request, body: dict) -> dict:
        """Enqueue a task into the channel and return an acceptance receipt.

        Request body fields:
            text        (str, required) — task description.
            session_id  (str, optional) — caller-supplied session identifier.

        Returns:
            {"status": "accepted", "task_id": "<uuid>"}
        """
        ip = request.client.host if request.client else "unknown"
        if not _check_rate_limit(ip):
            _metrics["tasks_rejected_rate"] += 1
            raise HTTPException(status_code=429, detail="Rate limit exceeded — slow down")
        task_id = str(uuid.uuid4())
        task = {
            "task_id": task_id,
            "text": body.get("text", ""),
            "attachments": body.get("attachments", []),
            "session_id": body.get("session_id", settings.profile_name),
        }
        if not channel.try_enqueue(task):
            _metrics["tasks_rejected_full"] += 1
            raise HTTPException(status_code=429, detail="Task queue full — try again later")
        _metrics["tasks_accepted"] += 1
        return {"status": "accepted", "task_id": task_id}

    @app.get("/status")
    async def status() -> dict:
        """Return runtime health information.

        Returns:
            {"status": "running", "agent": "<name>", "port": <port>}
        """
        return {
            "status": "running",
            "agent": settings.agent_name,
            "port": settings.agent_port,
        }

    @app.post("/message", dependencies=[__import__("fastapi").Depends(_check_token)])
    async def message(request: Request, body: dict) -> dict:
        """Receive an inbound message (future: Telegram / webhook).

        For now this is functionally identical to POST /task.

        Returns:
            {"status": "accepted", "task_id": "<uuid>"}
        """
        ip = request.client.host if request.client else "unknown"
        if not _check_rate_limit(ip):
            _metrics["tasks_rejected_rate"] += 1
            raise HTTPException(status_code=429, detail="Rate limit exceeded — slow down")
        task_id = str(uuid.uuid4())
        task = {
            "task_id": task_id,
            "text": body.get("text", ""),
            "attachments": body.get("attachments", []),
            "session_id": body.get("session_id", settings.profile_name),
        }
        if not channel.try_enqueue(task):
            _metrics["tasks_rejected_full"] += 1
            raise HTTPException(status_code=429, detail="Task queue full — try again later")
        _metrics["tasks_accepted"] += 1
        return {"status": "accepted", "task_id": task_id}

    @app.get("/metrics")
    async def metrics() -> Response:
        """Expose Prometheus-format counters and gauges.

        Returns:
            Plain text in Prometheus exposition format (text/plain; version=0.0.4).
        """
        return Response(
            content=_prometheus_text(channel),
            media_type="text/plain; version=0.0.4",
        )

    return app


async def start_server(app: FastAPI, port: int) -> None:
    """Start the uvicorn server and block until it exits.

    Args:
        app:  The FastAPI application to serve.
        port: TCP port to listen on (bound to 0.0.0.0).
    """
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="error")
    server = uvicorn.Server(config)
    await server.serve()
