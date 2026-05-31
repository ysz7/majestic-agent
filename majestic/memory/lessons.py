import sqlite3
import threading
from datetime import datetime, timezone

from majestic.storage import Store


class LessonsStore(Store):
    def __init__(self, db_path: str):
        super().__init__(db_path)
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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS skill_scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_name TEXT NOT NULL,
                    score REAL NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signal_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signals_text TEXT NOT NULL,
                    prediction_summary TEXT NOT NULL,
                    avg_confidence REAL DEFAULT 0.0,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS signal_patterns_fts
                USING fts5(signals_text, content='signal_patterns', content_rowid='id')
            """)

    def _get_conn(self):
        return self._conn

    def save(self, task_type: str, lesson: str):
        with self._lock:
            with self._get_conn() as conn:
                cur = conn.execute(
                    "INSERT INTO lessons (task_type, lesson, created_at) VALUES (?, ?, ?)",
                    (task_type, lesson, datetime.now(timezone.utc).isoformat()),
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
                    (skill_name, score, datetime.now(timezone.utc).isoformat()),
                )

    def get_skill_scores(self, skill_name: str, limit: int = 10) -> list[float]:
        """Return recent quality scores for a skill, newest first."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT score FROM skill_scores WHERE skill_name = ? ORDER BY id DESC LIMIT ?",
                (skill_name, limit),
            ).fetchall()
        return [r[0] for r in rows]

    def save_signal_pattern(
        self,
        signals: list[str],
        prediction_summary: str,
        avg_confidence: float = 0.0,
    ) -> None:
        """Save a set of signals + prediction excerpt for future cross-run recall."""
        signals_text = "\n".join(s.strip() for s in signals if s.strip())
        if not signals_text:
            return
        with self._lock:
            with self._get_conn() as conn:
                cur = conn.execute(
                    "INSERT INTO signal_patterns (signals_text, prediction_summary, avg_confidence, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (signals_text, prediction_summary[:600], avg_confidence,
                     datetime.now(timezone.utc).isoformat()),
                )
                rowid = cur.lastrowid
                conn.execute(
                    "INSERT INTO signal_patterns_fts(rowid, signals_text) VALUES (?, ?)",
                    (rowid, signals_text),
                )

    def search_signal_patterns(self, query: str, limit: int = 3) -> list[dict]:
        """FTS5 search over historical signal patterns — 0 LLM calls.

        Uses OR between query terms so any keyword match is sufficient.
        """
        words = [w.strip() for w in query.split() if len(w.strip()) > 3][:12]
        if not words:
            return []
        fts_query = " OR ".join(words)
        with self._get_conn() as conn:
            try:
                rows = conn.execute(
                    """
                    SELECT sp.id, sp.signals_text, sp.prediction_summary,
                           sp.avg_confidence, sp.created_at
                    FROM signal_patterns_fts f
                    JOIN signal_patterns sp ON sp.id = f.rowid
                    WHERE signal_patterns_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (fts_query, limit),
                ).fetchall()
            except Exception:
                rows = []
        return [
            {
                "id": r[0],
                "signals_text": r[1],
                "prediction_summary": r[2],
                "avg_confidence": r[3],
                "created_at": r[4],
            }
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
