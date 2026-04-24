"""
Tool registry — auto-registers all tools on import.

Usage in agent loop:
    from majestic.tools.registry import get_schemas, execute
    import majestic.tools  # noqa — triggers registration of all tools
"""
from . import web, research  # noqa: F401 — side-effect: populates registry

from .registry import get_schemas, execute  # re-export for convenience

__all__ = ["get_schemas", "execute"]
