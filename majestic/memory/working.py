"""
Working memory — in-memory session store for conversation messages and key/value data.
Scoped to a single agent session; no persistence between restarts.
"""

import threading
from typing import Any


class WorkingMemory:
    """Ephemeral, in-process memory that lives for the duration of one agent session."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}
        self._messages: list[dict] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Conversation messages
    # ------------------------------------------------------------------

    def add_message(self, role: str, content: str) -> None:
        """Append a conversation turn.

        Args:
            role: Typically "user", "assistant", or "system".
            content: Text content of the message.
        """
        with self._lock:
            self._messages.append({"role": role, "content": content})

    def get_messages(self) -> list[dict]:
        """Return a shallow copy of all conversation messages in order."""
        with self._lock:
            return list(self._messages)

    def clear_messages(self) -> None:
        """Remove all conversation messages (e.g. on context reset)."""
        with self._lock:
            self._messages.clear()

    # ------------------------------------------------------------------
    # Key/value scratchpad
    # ------------------------------------------------------------------

    def set(self, key: str, value: Any) -> None:
        """Store an arbitrary value under *key*.

        Args:
            key: Lookup key (string).
            value: Any Python object.
        """
        with self._lock:
            self._store[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value by key, returning *default* if absent.

        Args:
            key: Lookup key.
            default: Fallback value when key is missing.

        Returns:
            Stored value or *default*.
        """
        with self._lock:
            return self._store.get(key, default)

    def delete(self, key: str) -> None:
        """Remove a key from the scratchpad (no-op if absent).

        Args:
            key: Key to remove.
        """
        with self._lock:
            self._store.pop(key, None)

    def keys(self) -> list[str]:
        """Return the list of all scratchpad keys."""
        with self._lock:
            return list(self._store.keys())

    def clear_store(self) -> None:
        """Wipe the entire scratchpad."""
        with self._lock:
            self._store.clear()

    def clear(self) -> None:
        """Clear both messages and the scratchpad."""
        with self._lock:
            self._messages.clear()
            self._store.clear()

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<WorkingMemory messages={len(self._messages)} "
            f"store_keys={len(self._store)}>"
        )
