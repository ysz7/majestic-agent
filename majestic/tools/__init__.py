"""
Tool registry — auto-registers all tools on import.

Usage in agent loop:
    import majestic.tools  # triggers registration of all tools
    from majestic.tools.registry import get_schemas, execute
"""
from . import web, research, files, system  # noqa: F401 — side-effect: populates registry
from . import db_search, history_search      # noqa: F401
from majestic.agent import delegate          # noqa: F401 — registers delegate_task, delegate_parallel

# Load MCP servers defined in config (no-op if none configured)
try:
    from majestic.mcp.bridge import load_all_servers as _load_mcp
    _load_mcp()
except Exception:
    pass

from .registry import get_schemas, execute   # re-export for convenience

__all__ = ["get_schemas", "execute"]
