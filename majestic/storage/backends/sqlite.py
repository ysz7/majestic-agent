"""SQLite implementation of :class:`StorageBackend`.

Wraps the existing store classes — they remain the SQLite adapters behind the
backend contract. Paths come from ``settings.db_path()`` (tiered layout).
Imports are local to keep startup light and avoid import cycles.
"""

from __future__ import annotations

from typing import Any

from majestic.storage.backends import StorageBackend


class SqliteBackend(StorageBackend):
    """Hands out SQLite-backed stores, one file per logical DB name."""

    # ── intel tier ───────────────────────────────────────────────────────────
    def pains(self) -> Any:
        from majestic.tools.pains.db import PainsDB

        return PainsDB(self.settings.db_path("pains"))

    def research(self) -> Any:
        from majestic.tools.research.db import ResearchDB

        return ResearchDB(self.settings.db_path("research"))

    # ── memory tier ──────────────────────────────────────────────────────────
    def episodic(self) -> Any:
        from majestic.memory.episodic import EpisodicMemory

        return EpisodicMemory(self.settings.db_path("episodic"))

    def semantic(self) -> Any:
        from majestic.memory.semantic import SemanticMemory

        return SemanticMemory(self.settings.db_path("semantic"))

    def lessons(self) -> Any:
        from majestic.memory.lessons import LessonsStore

        return LessonsStore(self.settings.db_path("lessons"))

    def user_profile(self) -> Any:
        from majestic.memory.user_profile import UserProfile

        return UserProfile(self.settings.db_path("user_profile"))

    def script_tracker(self) -> Any:
        from majestic.evolution.script_tracker import ScriptTracker

        return ScriptTracker(self.settings.db_path("script_tracker"))

    # ── runtime tier ─────────────────────────────────────────────────────────
    def checkpoints(self) -> Any:
        from majestic.memory.checkpoints import CheckpointStore

        return CheckpointStore(self.settings.db_path("checkpoints"))

    def working(self, session_id: str | None = None) -> Any:
        from majestic.memory.working import WorkingMemory

        # Persistent only when enabled in persona.yaml; otherwise in-memory.
        db = self.settings.db_path("working") if self.settings.working_persistent else None
        return WorkingMemory(db_path=db, session_id=session_id)
