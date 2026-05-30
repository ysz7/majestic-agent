"""SQLite connection setup + small migration helpers, shared by all stores.

Before this module each store opened its own ``sqlite3.connect`` and repeated
the same ``PRAGMA`` lines. Centralizing it removes that duplication and gives
the project one place to change when an external DB backend is added (P-01).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(
    db_path: str,
    *,
    wal: bool = True,
    row_factory: bool = False,
    foreign_keys: bool = False,
) -> sqlite3.Connection:
    """Open a SQLite connection with the project's standard configuration.

    Args:
        db_path: Path to the SQLite file, or ``":memory:"`` for a transient DB.
        wal: Enable WAL journal mode (better concurrency for readers).
        row_factory: Set ``sqlite3.Row`` so rows are mapping-accessible.
        foreign_keys: Enforce foreign-key constraints.
    """
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    if row_factory:
        conn.row_factory = sqlite3.Row
    if wal:
        conn.execute("PRAGMA journal_mode=WAL;")
    if foreign_keys:
        conn.execute("PRAGMA foreign_keys=ON;")
    return conn


class Store:
    """Base class for SQLite-backed stores.

    Subclasses call ``super().__init__(db_path, ...)`` and then build their
    schema against ``self._conn``.
    """

    def __init__(
        self,
        db_path: str,
        *,
        wal: bool = True,
        row_factory: bool = False,
        foreign_keys: bool = False,
    ) -> None:
        self._db_path = db_path
        self._conn = connect(
            db_path,
            wal=wal,
            row_factory=row_factory,
            foreign_keys=foreign_keys,
        )

    # ── migration helpers ──────────────────────────────────────────────────

    def table_columns(self, table: str) -> set[str]:
        """Return the set of column names for *table* (empty set if missing)."""
        return {row[1] for row in self._conn.execute(f"PRAGMA table_info({table})")}

    def add_column_if_missing(self, table: str, column: str, ddl: str) -> bool:
        """``ALTER TABLE`` to add *column* when absent.

        Args:
            table: Target table name.
            column: Column name to check for.
            ddl: Column definition appended after ``ADD COLUMN``
                 (e.g. ``"score REAL DEFAULT 0.0"``).

        Returns:
            ``True`` if the column was added, ``False`` if it already existed.
        """
        if column not in self.table_columns(table):
            self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
            self._conn.commit()
            return True
        return False

    def close(self) -> None:
        self._conn.close()
