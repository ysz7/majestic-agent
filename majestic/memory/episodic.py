"""
Episodic memory — persistent task history stored in SQLite with FTS5 full-text search.

Schema
------
tasks
    id          INTEGER PRIMARY KEY AUTOINCREMENT
    timestamp   TEXT    (ISO-8601, UTC)
    task        TEXT    — original task description
    result      TEXT    — final result / output
    reflection  TEXT    — agent's self-assessment (optional)
    tokens_used INTEGER
    cost        REAL    (USD)
    duration_s  REAL    (wall-clock seconds)

tasks_fts  (FTS5 virtual table, content=tasks)
    task, result, reflection
"""

import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any


_CREATE_TASKS = """
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    task        TEXT    NOT NULL,
    result      TEXT    NOT NULL DEFAULT '',
    reflection  TEXT    NOT NULL DEFAULT '',
    tokens_used INTEGER NOT NULL DEFAULT 0,
    cost        REAL    NOT NULL DEFAULT 0.0,
    duration_s  REAL    NOT NULL DEFAULT 0.0
);
"""

_CREATE_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS tasks_fts
USING fts5(
    task,
    result,
    reflection,
    content=tasks,
    content_rowid=id
);
"""

# Keep FTS in sync via triggers
_CREATE_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS tasks_ai AFTER INSERT ON tasks BEGIN
    INSERT INTO tasks_fts(rowid, task, result, reflection)
    VALUES (new.id, new.task, new.result, new.reflection);
END;

CREATE TRIGGER IF NOT EXISTS tasks_ad AFTER DELETE ON tasks BEGIN
    INSERT INTO tasks_fts(tasks_fts, rowid, task, result, reflection)
    VALUES ('delete', old.id, old.task, old.result, old.reflection);
END;

CREATE TRIGGER IF NOT EXISTS tasks_au AFTER UPDATE ON tasks BEGIN
    INSERT INTO tasks_fts(tasks_fts, rowid, task, result, reflection)
    VALUES ('delete', old.id, old.task, old.result, old.reflection);
    INSERT INTO tasks_fts(rowid, task, result, reflection)
    VALUES (new.id, new.task, new.result, new.reflection);
END;
"""


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


class EpisodicMemory:
    """Persistent log of completed tasks with full-text search via FTS5."""

    def __init__(self, db_path: str) -> None:
        """Open (or create) the SQLite database at *db_path*.

        Args:
            db_path: Filesystem path to the SQLite file.
                     Use ``":memory:"`` for an in-process ephemeral store.
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
            self._conn.execute(_CREATE_TASKS)
            self._conn.execute(_CREATE_FTS)
            for stmt in _CREATE_TRIGGERS.strip().split("END;"):
                stmt = stmt.strip()
                if stmt:
                    self._conn.execute(stmt + " END;")

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save_task(
        self,
        task: str,
        result: str,
        reflection: str = "",
        tokens_used: int = 0,
        cost: float = 0.0,
        duration_s: float = 0.0,
    ) -> int:
        """Persist a completed task record.

        Args:
            task: Natural-language description of the task.
            result: Output / answer produced by the agent.
            reflection: Optional self-critique or lesson learned.
            tokens_used: Total tokens consumed (prompt + completion).
            cost: Estimated cost in USD.
            duration_s: Wall-clock time in seconds.

        Returns:
            The rowid of the newly inserted record.
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT INTO tasks (timestamp, task, result, reflection,
                                   tokens_used, cost, duration_s)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (timestamp, task, result, reflection, tokens_used, cost, duration_s),
            )
            self._conn.commit()
            return cursor.lastrowid  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """Full-text search over task, result, and reflection fields.

        Uses SQLite FTS5 BM25 ranking (lower score = better match).

        Args:
            query: FTS5 query string (e.g. ``"python error"``, ``'"exact phrase"'``).
            limit: Maximum number of results to return.

        Returns:
            List of task dicts ordered by relevance, best match first.
        """
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT t.id, t.timestamp, t.task, t.result, t.reflection,
                       t.tokens_used, t.cost, t.duration_s
                FROM tasks_fts
                JOIN tasks t ON tasks_fts.rowid = t.id
                WHERE tasks_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_recent(self, limit: int = 10) -> list[dict]:
        """Return the most recently saved tasks in reverse chronological order.

        Args:
            limit: Maximum number of records to return.

        Returns:
            List of task dicts, newest first.
        """
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, timestamp, task, result, reflection,
                       tokens_used, cost, duration_s
                FROM tasks
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_by_id(self, task_id: int) -> dict | None:
        """Fetch a single task record by primary key.

        Args:
            task_id: The ``id`` column value.

        Returns:
            Task dict or ``None`` if not found.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        return _row_to_dict(row) if row else None

    def count(self) -> int:
        """Return the total number of stored task records."""
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying database connection."""
        with self._lock:
            self._conn.close()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<EpisodicMemory db={self._db_path!r}>"
