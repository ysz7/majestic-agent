"""Shared authentication dependency for the desktop API."""

from __future__ import annotations

from pathlib import Path

from fastapi import Header, HTTPException

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def _load_token() -> str:
    path = _PROJECT_ROOT / "data" / "agent_token"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


async def require_token(x_agent_token: str | None = Header(default=None)) -> None:
    token = _load_token()
    if token and x_agent_token != token:
        raise HTTPException(status_code=401, detail="Unauthorized")
