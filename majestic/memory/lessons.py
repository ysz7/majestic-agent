import sqlite3
import threading
from datetime import datetime


class LessonsStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS lessons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_type TEXT,
                    lesson TEXT,
                    usage_count INTEGER DEFAULT 0,
                    created_at TEXT
                )
            """)
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS lessons_fts
                USING fts5(lesson, content='lessons', content_rowid='id')
            """)

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def save(self, task_type: str, lesson: str):
        with self._lock:
            with self._get_conn() as conn:
                cur = conn.execute(
                    "INSERT INTO lessons (task_type, lesson, created_at) VALUES (?, ?, ?)",
                    (task_type, lesson, datetime.utcnow().isoformat()),
                )
                rowid = cur.lastrowid
                conn.execute(
                    "INSERT INTO lessons_fts(rowid, lesson) VALUES (?, ?)",
                    (rowid, lesson),
                )

    def search(self, query: str, limit: int = 3) -> list[dict]:
        """Search lessons relevant to the query using FTS5."""
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT l.id, l.task_type, l.lesson, l.usage_count, l.created_at
                FROM lessons_fts f
                JOIN lessons l ON l.id = f.rowid
                WHERE lessons_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
            # Increment usage count
            for row in rows:
                conn.execute(
                    "UPDATE lessons SET usage_count = usage_count + 1 WHERE id = ?",
                    (row[0],),
                )
            return [
                {"id": r[0], "task_type": r[1], "lesson": r[2], "usage_count": r[3]}
                for r in rows
            ]

    def get_top(self, task_type: str = None, limit: int = 3) -> list[dict]:
        """Get most-used lessons, optionally filtered by task_type."""
        with self._get_conn() as conn:
            if task_type:
                rows = conn.execute(
                    "SELECT id, task_type, lesson, usage_count FROM lessons "
                    "WHERE task_type = ? ORDER BY usage_count DESC LIMIT ?",
                    (task_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, task_type, lesson, usage_count FROM lessons "
                    "ORDER BY usage_count DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [
                {"id": r[0], "task_type": r[1], "lesson": r[2], "usage_count": r[3]}
                for r in rows
            ]
