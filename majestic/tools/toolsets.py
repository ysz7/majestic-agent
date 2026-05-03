"""
Named toolsets — pre-defined groups of tools for specific use cases.

Usage:
  from majestic.tools.toolsets import apply_toolset, list_toolsets
  apply_toolset("research")     # disables all tools not in the research set
  list_toolsets()               # returns {name: [tool_names]}
"""
from __future__ import annotations

_DEFAULT_TOOLSETS: dict[str, list[str]] = {
    "research": [
        "search_knowledge", "search_web", "run_research",
        "get_briefing", "get_news", "get_report", "generate_ideas",
        "get_market_data", "read_file",
        "workspace_list", "workspace_search",
        "db_search", "history_search",
    ],
    "coding": [
        "read_file", "write_file", "run_command", "run_python",
        "http_request", "get_datetime", "remember", "copy_file",
        "save_script", "list_scripts", "run_script",
        "search_knowledge", "search_web", "db_search",
        "workspace_list", "workspace_search", "workspace_delete", "workspace_move",
        "index_file",
    ],
    "market": [
        "get_market_data", "search_web", "get_briefing",
        "get_news", "db_search", "search_knowledge",
        "generate_ideas",
    ],
    "minimal": [
        "search_web", "search_knowledge",
        "read_file", "write_file", "db_search",
    ],
    "full": [],  # empty = all tools active
}


def list_toolsets() -> dict[str, list[str]]:
    """Return available toolsets — built-in defaults merged with any from config."""
    try:
        from majestic import config as cfg
        custom = cfg.get("agent.toolsets") or {}
        return {**_DEFAULT_TOOLSETS, **custom}
    except Exception:
        return dict(_DEFAULT_TOOLSETS)


def apply_toolset(name: str) -> bool:
    """
    Activate a toolset: disable all tools NOT in the set.
    'full' clears all restrictions.
    Returns True if the toolset name was found.
    """
    toolsets = list_toolsets()
    if name not in toolsets:
        return False

    from majestic import config as cfg
    keep = toolsets[name]

    if not keep:  # "full" or empty = no restrictions
        cfg.set_value("agent.tools_disabled", [])
        cfg.set_value("agent.tools_enabled", [])
        return True

    # Import registry lazily to avoid circular import at module load
    try:
        from majestic.tools.registry import _registry
        all_names = set(_registry.keys())
    except Exception:
        all_names = set()

    disabled = sorted(all_names - set(keep))
    cfg.set_value("agent.tools_disabled", disabled)
    cfg.set_value("agent.tools_enabled", [])
    return True


def current_toolset() -> str | None:
    """Guess the active toolset name from current tools_disabled config, or None."""
    try:
        from majestic import config as cfg
        disabled = set(cfg.get("agent.tools_disabled", []) or [])
        enabled  = cfg.get("agent.tools_enabled", []) or []
        if enabled:
            return None  # using whitelist, not a toolset
        if not disabled:
            return "full"
        toolsets = list_toolsets()
        try:
            from majestic.tools.registry import _registry
            all_names = set(_registry.keys())
        except Exception:
            return None
        for ts_name, ts_tools in toolsets.items():
            if not ts_tools:
                continue
            expected_disabled = all_names - set(ts_tools)
            if expected_disabled == disabled:
                return ts_name
    except Exception:
        pass
    return None


def get_active_tools() -> list[str]:
    """Return names of currently active (non-disabled) tools."""
    try:
        from majestic.tools.registry import _registry
        from majestic import config as cfg
        enabled  = cfg.get("agent.tools_enabled", []) or []
        disabled = set(cfg.get("agent.tools_disabled", []) or [])
        all_names = list(_registry.keys())
        if enabled:
            return [n for n in all_names if n in enabled]
        return [n for n in all_names if n not in disabled]
    except Exception:
        return []
