"""
Tool registry — auto-registers all tools on import.

Usage in agent loop:
    import majestic.tools  # triggers registration of all tools
    from majestic.tools.registry import get_schemas, execute
"""
from . import web, research, files, system, code  # noqa: F401 — side-effect: populates registry
from . import db_search, history_search            # noqa: F401
from . import memory_tool, email_tool              # noqa: F401
from majestic.agent import delegate          # noqa: F401 — registers delegate_task, delegate_parallel

# Load MCP servers defined in config (no-op if none configured)
try:
    from majestic.mcp.bridge import load_all_servers as _load_mcp
    _load_mcp()
except Exception:
    pass

# Auto-load user-defined tools from majestic/tools/local/*.py
try:
    import importlib.util as _ilu
    from pathlib import Path as _Path
    _local_dir = _Path(__file__).parent / "local"
    for _f in sorted(_local_dir.glob("*.py")):
        _spec = _ilu.spec_from_file_location(f"majestic.tools.local.{_f.stem}", _f)
        if _spec and _spec.loader:
            _mod = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
except Exception:
    pass

from .registry import get_schemas, execute   # re-export for convenience

__all__ = ["get_schemas", "execute"]
