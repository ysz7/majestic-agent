"""Slash-command package — registry, context, and dispatcher.

Each command lives in its own module and self-registers via
``@command("/name")``. :func:`dispatch` routes a :class:`CommandContext` to the
matching handler, returning ``None`` for unknown commands so the caller can fall
back to skill invocation / agent handling.
"""

from __future__ import annotations

from majestic.cli.commands.context import CommandContext
from majestic.cli.commands.registry import get_handler, registered

# Import command modules so their @command decorators run and register handlers.
from majestic.cli.commands import (  # noqa: F401,E402
    agents as _agents,
    ask as _ask,
    briefing as _briefing,
    budget as _budget,
    goodmorning as _goodmorning,
    help as _help,
    ideas as _ideas,
    memory as _memory,
    new as _new,
    news as _news,
    pains as _pains,
    predict as _predict,
    research as _research,
    skills as _skills,
    tools as _tools,
)

__all__ = ["CommandContext", "dispatch", "get_handler", "registered"]


async def dispatch(ctx: CommandContext):
    """Run the handler for ``ctx.cmd``; return ``None`` if no command matches."""
    handler = get_handler(ctx.cmd)
    if handler is None:
        return None
    return await handler(ctx)
