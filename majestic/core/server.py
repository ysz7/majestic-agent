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

import uuid

from fastapi import FastAPI
import uvicorn


def create_app(channel, settings) -> FastAPI:
    """Build and return the FastAPI application.

    Args:
        channel: A channel instance with an async ``enqueue(task: dict)`` method.
        settings: A Settings object exposing ``agent_name`` and ``agent_port``.

    Returns:
        Configured FastAPI application (not yet running).
    """
    app = FastAPI(title="Majestic Agent Server")

    @app.post("/task")
    async def receive_task(body: dict) -> dict:
        """Enqueue a task into the channel and return an acceptance receipt.

        Request body fields:
            text        (str, required) — task description.
            session_id  (str, optional) — caller-supplied session identifier.

        Returns:
            {"status": "accepted", "task_id": "<uuid>"}
        """
        task_id = str(uuid.uuid4())
        task = {
            "task_id": task_id,
            "text": body.get("text", ""),
            "attachments": body.get("attachments", []),
            "session_id": body.get("session_id", settings.profile_name),
        }
        await channel.enqueue(task)
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

    @app.post("/message")
    async def message(body: dict) -> dict:
        """Receive an inbound message (future: Telegram / webhook).

        For now this is functionally identical to POST /task.

        Returns:
            {"status": "accepted", "task_id": "<uuid>"}
        """
        task_id = str(uuid.uuid4())
        task = {
            "task_id": task_id,
            "text": body.get("text", ""),
            "attachments": body.get("attachments", []),
            "session_id": body.get("session_id", settings.profile_name),
        }
        await channel.enqueue(task)
        return {"status": "accepted", "task_id": task_id}

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
