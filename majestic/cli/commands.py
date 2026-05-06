"""
Slash command registry.

Maps command names to the underlying tool + description.

  dispatch(cmd, args) → str   — execute a command, return raw text
  SHORTCUTS             dict  — {name: (tool_name, description)}
"""

SHORTCUTS: dict[str, tuple[str, str]] = {
    "news":   ("get_news",   "Latest indexed news"),
    "report": ("get_report", "Deep report on a topic"),
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
