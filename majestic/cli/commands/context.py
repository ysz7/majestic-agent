"""CommandContext — everything a slash-command handler needs, in one object.

Replaces the long positional argument list that handlers used to receive, and
carries the `out()` printer so handlers don't redefine it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CommandContext:
    text: str
    profile_name: str
    working_memory: Any
    runtime: Any
    settings: Any = None
    semantic: Any = None
    channel: Any = None
    gateway: Any = None
    backend: Any = None
    console: Any = None

    @property
    def cmd(self) -> str:
        """The leading slash token, lowercased (e.g. ``/research``)."""
        return self.text.strip().lower().split()[0]

    def out(self, markup: str) -> None:
        """Print via Rich console when available, else plain print."""
        if self.console:
            self.console.print(markup)
        else:
            print(markup)
