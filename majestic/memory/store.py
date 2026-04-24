"""
Persistent memory backed by two Markdown files in MAJESTIC_HOME/memory/:

  memory.md — agent facts: knowledge, tasks, context learned over time
  user.md   — user profile: preferences, habits, background

Both files are plain Markdown. Entries are freeform paragraphs or bullet lists.
/forget removes entries by keyword match.
"""
import re
from pathlib import Path
from typing import Optional

from majestic.constants import MEMORY_DIR

MEMORY_FILE = MEMORY_DIR / "memory.md"
USER_FILE   = MEMORY_DIR / "user.md"

_MEMORY_HEADER = "# Agent Memory\n\n"
_USER_HEADER   = "# User Profile\n\n"


def _ensure(path: Path, header: str) -> None:
    if not path.exists():
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(header, encoding="utf-8")


def load_memory() -> str:
    _ensure(MEMORY_FILE, _MEMORY_HEADER)
    text = MEMORY_FILE.read_text(encoding="utf-8")
    return text.removeprefix(_MEMORY_HEADER).strip()


def load_user() -> str:
    _ensure(USER_FILE, _USER_HEADER)
    text = USER_FILE.read_text(encoding="utf-8")
    return text.removeprefix(_USER_HEADER).strip()


def load_both() -> str:
    """Return combined memory block for injection into system prompt."""
    mem  = load_memory()
    user = load_user()
    parts = []
    if user:
        parts.append(f"## User Profile\n{user}")
    if mem:
        parts.append(f"## Agent Memory\n{mem}")
    return "\n\n".join(parts)


def append_memory(text: str) -> None:
    """Append a new entry to memory.md."""
    _ensure(MEMORY_FILE, _MEMORY_HEADER)
    current = MEMORY_FILE.read_text(encoding="utf-8")
    entry   = text.strip()
    if entry not in current:
        MEMORY_FILE.write_text(current.rstrip() + "\n\n" + entry + "\n", encoding="utf-8")


def append_user(text: str) -> None:
    """Append a new entry to user.md."""
    _ensure(USER_FILE, _USER_HEADER)
    current = USER_FILE.read_text(encoding="utf-8")
    entry   = text.strip()
    if entry not in current:
        USER_FILE.write_text(current.rstrip() + "\n\n" + entry + "\n", encoding="utf-8")


def forget(topic: str) -> int:
    """
    Remove all paragraphs/bullets from both files that mention <topic>.
    Returns number of entries removed.
    """
    removed = 0
    for path in (MEMORY_FILE, USER_FILE):
        if not path.exists():
            continue
        text  = path.read_text(encoding="utf-8")
        lines = text.split("\n")
        kw    = topic.lower()

        # Split into blocks (paragraphs separated by blank lines)
        blocks: list[list[str]] = []
        current: list[str] = []
        for line in lines:
            if line.strip() == "" and current:
                blocks.append(current)
                blocks.append([""])
                current = []
            else:
                current.append(line)
        if current:
            blocks.append(current)

        new_blocks = []
        for block in blocks:
            block_text = "\n".join(block).lower()
            if kw in block_text and not any(
                line.startswith("#") for line in block
            ):
                removed += 1
            else:
                new_blocks.append(block)

        path.write_text("\n".join("\n".join(b) for b in new_blocks), encoding="utf-8")

    return removed


def show() -> str:
    """Return formatted memory for display to user."""
    mem  = load_memory()
    user = load_user()
    parts = []
    if user:
        parts.append(f"**User Profile** ({USER_FILE})\n\n{user}")
    else:
        parts.append(f"**User Profile** — empty")
    if mem:
        parts.append(f"**Agent Memory** ({MEMORY_FILE})\n\n{mem}")
    else:
        parts.append(f"**Agent Memory** — empty")
    return "\n\n---\n\n".join(parts)
