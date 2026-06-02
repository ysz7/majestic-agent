"""Slash-command registry — decorator + lookup, no other deps (avoids cycles)."""

from __future__ import annotations

from typing import Awaitable, Callable

from majestic.cli.commands.context import CommandContext

Handler = Callable[[CommandContext], Awaitable[object]]

_REGISTRY: dict[str, Handler] = {}


def command(name: str) -> Callable[[Handler], Handler]:
    """Register an async handler for a slash command (e.g. ``@command("/help")``)."""
    def deco(fn: Handler) -> Handler:
        _REGISTRY[name] = fn
        return fn
    return deco


def get_handler(name: str) -> Handler | None:
    return _REGISTRY.get(name)


def registered() -> list[str]:
    return sorted(_REGISTRY)
