"""
Tool registry — auto-registration via @tool decorator.

Each tool module imports this and uses @tool to register itself.
The registry is populated on import of majestic.tools.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

_registry: dict[str, "_Tool"] = {}


@dataclass
class _Tool:
    name: str
    description: str
    input_schema: dict
    fn: Callable


def tool(name: str, description: str, input_schema: dict):
    """Decorator — registers a function as a callable tool."""
    def decorator(fn: Callable) -> Callable:
        _registry[name] = _Tool(name, description, input_schema, fn)
        return fn
    return decorator


def get_schemas() -> list[dict]:
    """Return tool definitions in Anthropic format for LLM tool_use."""
    return [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema}
        for t in _registry.values()
    ]


def execute(name: str, arguments: dict) -> str:
    t = _registry.get(name)
    if not t:
        return f"[tool error] Unknown tool: {name!r}"
    try:
        result = t.fn(**arguments)
        return str(result) if result is not None else "(no output)"
    except Exception as e:
        return f"[tool error] {name}: {e}"
