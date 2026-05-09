"""
Checkpoint store — crash-recovery snapshots for long-running agent tasks.

Each task execution is broken into numbered steps.  After every step the agent
calls ``save_step``; if the process crashes it can resume from ``load_latest``
instead of restarting from scratch.  Completed tasks are pruned automatically
via ``cleanup_old``.

Schema
------
checkpoints
    id          INTEGER PRIMARY KEY AUTOINCREMENT
    task_id     TEXT    NOT NULL         — caller-supplied task identifier
    step_num    INTEGER NOT NULL         — 0-based step index
    step_data   TEXT    NOT NULL         — JSON-encoded step payload
    created_at  TEXT    NOT NULL         — ISO-8601 UTC timestamp

Unique constraint on (task_id, step_num) — later writes for the same step
overwrite the previous record via INSERT OR REPLACE.
"""

import json
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from typing import Any


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS checkpoints (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    TEXT    NOT NULL,
    step_num   INTEGER NOT NULL,
    step_data  TEXT    NOT NULL DEFAULT '{}',
    created_at TEXT    NOT NULL,
    UNIQUE (task_id, step_num)
);
"""

_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_checkpoints_task_id
ON checkpoints (task_id, step_num DESC);
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class CheckpointStore:
    """SQLite-backed store for incremental task checkpoints."""

    def __init__(self, db_path: str) -> None:
        """Open (or create) the checkpoint database at *db_path*.

        Args:
            db_path: Filesystem path to the SQLite file.
                     Use ``":memory:"`` for a transient in-process store.
        """
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute(_CREATE_TABLE)
            self._conn.execute(_CREATE_INDEX)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save_step(
        self, task_id: str, step_num: int, step_data: dict[str, Any]
    ) -> None:
        """Persist (or overwrite) a checkpoint for *task_id* at *step_num*.

        If a record already exists for ``(task_id, step_num)`` it is replaced
        so that re-runs of the same step stay idempotent.

        Args:
            task_id: Unique identifier for the task (e.g. a UUID).
            step_num: Zero-based step index within the task.
            step_data: Arbitrary JSON-serialisable dict describing the step
                       state (e.g. intermediate results, context variables).
        """
        payload = json.dumps(step_data, ensure_ascii=False)
        now = _utcnow()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO checkpoints (task_id, step_num, step_data, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(task_id, step_num)
                DO UPDATE SET step_data=excluded.step_data,
                              created_at=excluded.created_at
                """,
                (task_id, step_num, payload, now),
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def load_latest(self, task_id: str) -> dict[str, Any] | None:
        """Return the highest-numbered checkpoint for *task_id*, or ``None``.

        The returned dict has the shape::

            {
                "task_id":   str,
                "step_num":  int,
                "step_data": dict,       # decoded from JSON
                "created_at": str,
            }

        Args:
            task_id: Task identifier to look up.

        Returns:
            Checkpoint dict for the latest step, or ``None`` if no checkpoint
            exists for *task_id*.
        """
        with self._lock:
            row = self._conn.execute(
                """
                SELECT task_id, step_num, step_data, created_at
                FROM checkpoints
                WHERE task_id = ?
                ORDER BY step_num DESC
                LIMIT 1
                """,
                (task_id,),
            ).fetchone()

        if row is None:
            return None

        return {
            "task_id": row["task_id"],
            "step_num": row["step_num"],
            "step_data": json.loads(row["step_data"]),
            "created_at": row["created_at"],
        }

    def load_step(self, task_id: str, step_num: int) -> dict[str, Any] | None:
        """Return a specific checkpoint by task and step number.

        Args:
            task_id: Task identifier.
            step_num: Step index to retrieve.

        Returns:
            Checkpoint dict or ``None`` if not found.
        """
        with self._lock:
            row = self._conn.execute(
                """
                SELECT task_id, step_num, step_data, created_at
                FROM checkpoints
                WHERE task_id = ? AND step_num = ?
                """,
                (task_id, step_num),
            ).fetchone()

        if row is None:
            return None

        return {
            "task_id": row["task_id"],
            "step_num": row["step_num"],
            "step_data": json.loads(row["step_data"]),
            "created_at": row["created_at"],
        }

    def list_steps(self, task_id: str) -> list[int]:
        """Return all persisted step numbers for *task_id* in ascending order.

        Args:
            task_id: Task identifier.

        Returns:
            Sorted list of step indices (may be empty).
        """
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT step_num FROM checkpoints
                WHERE task_id = ?
                ORDER BY step_num ASC
                """,
                (task_id,),
            ).fetchall()
        return [r["step_num"] for r in rows]

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    def complete_task(self, task_id: str) -> int:
        """Delete all checkpoints for a successfully completed task.

        Call this after the agent has confirmed success to free storage.

        Args:
            task_id: Task identifier whose checkpoints should be removed.

        Returns:
            Number of checkpoint rows deleted.
        """
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM checkpoints WHERE task_id = ?", (task_id,)
            )
            self._conn.commit()
            return cursor.rowcount

    def cleanup_old(self, days: int = 7) -> int:
        """Remove checkpoints older than *days* days.

        Intended for periodic housekeeping of checkpoints from tasks that
        crashed without calling ``complete_task``.

        Args:
            days: Retention window in days (default 7).

        Returns:
            Number of checkpoint rows deleted.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM checkpoints WHERE created_at < ?", (cutoff,)
            )
            self._conn.commit()
            return cursor.rowcount

    def count(self, task_id: str | None = None) -> int:
        """Return the number of stored checkpoint rows.

        Args:
            task_id: If given, count only rows for this task; otherwise count all.

        Returns:
            Row count.
        """
        with self._lock:
            if task_id is not None:
                return self._conn.execute(
                    "SELECT COUNT(*) FROM checkpoints WHERE task_id = ?", (task_id,)
                ).fetchone()[0]
            return self._conn.execute(
                "SELECT COUNT(*) FROM checkpoints"
            ).fetchone()[0]

    def close(self) -> None:
        """Close the underlying database connection."""
        with self._lock:
            self._conn.close()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CheckpointStore db={self._db_path!r}>"
