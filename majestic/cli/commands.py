"""
Slash command registry.

Maps command names to the underlying tool + description.
Used by CLI and Telegram to dispatch /research, /briefing, etc.

  dispatch(cmd, args) → str   — execute a command, return raw text
  SHORTCUTS             dict  — {name: (tool_name, description)}
"""

SHORTCUTS: dict[str, tuple[str, str]] = {
    "research": ("run_research",    "Collect intel from all sources"),
    "briefing": ("get_briefing",    "Full market/tech briefing"),
    "market":   ("get_market_data", "Crypto, stocks, forex snapshot"),
    "news":     ("get_news",        "Latest news sorted by CCW score"),
    "report":   ("get_report",      "Deep report on a topic"),
    "ideas":    ("generate_ideas",  "Business ideas from recent trends"),
}

MANAGEMENT: dict[str, str] = {
    "model":     "Switch LLM provider/model",
    "memory":    "View persistent memory",
    "forget":    "Remove a memory entry",
    "skills":    "List saved skills",
    "stop":      "Stop current agent task",
    "usage":     "Token usage and cost",
    "remind":    "Add a natural-language reminder",
    "reminders": "List active reminders",
    "rss":       "Manage RSS feeds",
    "reports":   "List saved reports",
}


def dispatch(cmd: str, args: dict | None = None) -> str:
    """Execute a shortcut command. Returns raw text result."""
    import majestic.tools as _tools
    entry = SHORTCUTS.get(cmd)
    if not entry:
        return f"Unknown command: /{cmd}"
    tool_name, _ = entry
    return _tools.execute(tool_name, args or {})


def all_command_names() -> list[str]:
    return list(SHORTCUTS) + list(MANAGEMENT)
