"""Tier layout: which DB belongs to which subfolder + one-time file migration.

Phase 9 reorganizes a profile's ``data/`` into three tiers:

    runtime/   disposable execution state (delete → fresh session, no loss)
    memory/    cognitive memory that accumulates across sessions
    intel/     collected data — the sellable asset

Existing flat ``data/<name>.db`` files are moved into their tier on first
access (auto-migration), so users keep their data without manual steps.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# Single source of truth: logical DB name → tier subfolder.
# Names absent here keep the flat ``data/<name>.db`` location.
DB_TIERS: dict[str, str] = {
    # runtime — disposable
    "working": "runtime",
    "checkpoints": "runtime",
    # memory — accumulates
    "episodic": "memory",
    "semantic": "memory",
    "lessons": "memory",
    "user_profile": "memory",
    "script_tracker": "memory",
    # intel — the asset
    "research": "intel",
    "pains": "intel",
}

# SQLite keeps the DB plus WAL/SHM sidecars; move them together to stay consistent.
_SIDECARS = ("", "-wal", "-shm")


def migrate_layout(data_dir: Path) -> int:
    """Move flat ``data/<name>.db`` into ``data/<tier>/<name>.db``.

    Idempotent: a DB is moved only when its flat file exists and the tiered
    target does not. WAL/SHM sidecars move with the main file. Returns the
    number of databases relocated.
    """
    moved = 0
    for name, tier in DB_TIERS.items():
        flat = data_dir / f"{name}.db"
        target_dir = data_dir / tier
        target = target_dir / f"{name}.db"
        if not flat.exists() or target.exists():
            continue  # nothing to move, or already migrated
        target_dir.mkdir(parents=True, exist_ok=True)
        for suffix in _SIDECARS:
            src = data_dir / f"{name}.db{suffix}"
            if src.exists():
                shutil.move(str(src), str(target_dir / f"{name}.db{suffix}"))
        moved += 1
        logger.info("Migrated %s.db → %s/", name, tier)
    return moved
