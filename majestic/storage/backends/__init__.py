"""Pluggable storage backends.

The :class:`StorageBackend` ABC is the contract every backend must satisfy —
it hands out the concrete store objects the app uses. :func:`get_backend`
selects an implementation from ``settings.db_backend``.

Today only the SQLite backend is wired. Adding PostgreSQL/Supabase later means:
implement a new ``StorageBackend`` subclass and register it in
:func:`get_backend` — no changes to memory, tools, or business logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # avoid import cost / cycles at runtime
    from majestic.config.settings import Settings


class StorageBackend(ABC):
    """Contract for a storage backend: a factory of store objects.

    Each method returns a store exposing the same public API regardless of the
    underlying database, so callers never touch the backend directly.
    """

    def __init__(self, settings: "Settings") -> None:
        self.settings = settings

    # ── intel tier (the sellable asset — first target for external DBs) ──────
    @abstractmethod
    def pains(self) -> Any: ...

    @abstractmethod
    def research(self) -> Any: ...

    # ── memory tier ──────────────────────────────────────────────────────────
    @abstractmethod
    def episodic(self) -> Any: ...

    @abstractmethod
    def semantic(self) -> Any: ...

    @abstractmethod
    def lessons(self) -> Any: ...

    @abstractmethod
    def user_profile(self) -> Any: ...

    @abstractmethod
    def script_tracker(self) -> Any: ...

    # ── runtime tier ─────────────────────────────────────────────────────────
    @abstractmethod
    def checkpoints(self) -> Any: ...

    @abstractmethod
    def working(self, session_id: str | None = None) -> Any: ...


def get_backend(settings: "Settings") -> StorageBackend:
    """Return the storage backend selected by ``settings.db_backend``.

    Raises ``NotImplementedError`` for backends that have no adapter yet.
    """
    name = getattr(settings, "db_backend", "sqlite")
    if name == "sqlite":
        from majestic.storage.backends.sqlite import SqliteBackend

        return SqliteBackend(settings)
    raise NotImplementedError(
        f"Storage backend '{name}' is not implemented yet. "
        f"Set MAJESTIC_DB_BACKEND=sqlite or add a StorageBackend adapter."
    )


__all__ = ["StorageBackend", "get_backend"]
