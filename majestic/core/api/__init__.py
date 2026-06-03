"""Desktop API — mounts all domain routers under /api prefix.

Usage in server.py::

    from majestic.core.api import create_desktop_router
    app.include_router(create_desktop_router())
"""

from __future__ import annotations

from fastapi import APIRouter

from .agents import router as agents_router
from .audit import router as audit_router
from .budget import router as budget_router
from .cron import router as cron_router
from .memory import router as memory_router
from .profiles import router as profiles_router
from .skills import router as skills_router
from .workspace import router as workspace_router
from .ws import router as ws_router


def create_desktop_router() -> APIRouter:
    """Return an APIRouter with all desktop API routes mounted under /api."""
    api = APIRouter(prefix="/api")
    api.include_router(profiles_router)
    api.include_router(agents_router)
    api.include_router(memory_router)
    api.include_router(skills_router)
    api.include_router(workspace_router)
    api.include_router(budget_router)
    api.include_router(cron_router)
    api.include_router(audit_router)
    return api


__all__ = ["create_desktop_router", "ws_router"]
