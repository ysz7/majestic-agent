import sqlite3
import threading
from datetime import datetime


class LessonsStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS skill_scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_name TEXT NOT NULL,
                    score REAL NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

    def _get_conn(self):
        return self._conn

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

    def save_skill_score(self, skill_name: str, score: float) -> None:
        """Persist a quality score for a skill execution."""
        with self._lock:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT INTO skill_scores (skill_name, score, created_at) VALUES (?, ?, ?)",
                    (skill_name, score, datetime.utcnow().isoformat()),
                )

    def get_skill_scores(self, skill_name: str, limit: int = 10) -> list[float]:
        """Return recent quality scores for a skill, newest first."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT score FROM skill_scores WHERE skill_name = ? ORDER BY id DESC LIMIT ?",
                (skill_name, limit),
            ).fetchall()
        return [r[0] for r in rows]

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
