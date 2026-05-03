"""Explicit memory tool — agent saves facts/preferences to persistent memory."""
from __future__ import annotations

from majestic.tools.registry import tool

_CATEGORIES = {"preference", "fact", "context", "goal", "general"}


@tool(
    name="remember",
    description=(
        "Save a fact, preference, or note to persistent memory for future sessions. "
        "Use when the user asks you to remember something, or when you learn something "
        "important that should persist across conversations."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The fact or preference to remember",
            },
            "category": {
                "type": "string",
                "description": "Category: preference, fact, context, goal, general (default: general)",
            },
            "target": {
                "type": "string",
                "description": "Where to save: 'memory' (agent knowledge) or 'user' (user profile). Default: memory",
            },
        },
        "required": ["content"],
    },
)
def remember(content: str, category: str = "general", target: str = "memory") -> str:
    from majestic.memory.store import append_memory, append_user

    cat = category if category in _CATEGORIES else "general"
    entry = f"[{cat}] {content.strip()}"

    if target == "user":
        append_user(entry)
        return f"Saved to user profile: {entry}"
    else:
        append_memory(entry)
        return f"Saved to memory: {entry}"
