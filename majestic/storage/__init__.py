"""Shared storage foundation — single owner of SQLite connection setup.

Every memory/tool store builds on :class:`Store` (or the :func:`connect`
helper), so connection pragmas live in exactly one place. This is also the
single seam to swap for an external backend later (see PLAN.md Phase 11).
"""

from majestic.storage.base import Store, connect
from majestic.storage.backends import StorageBackend, get_backend

__all__ = ["Store", "connect", "StorageBackend", "get_backend"]
