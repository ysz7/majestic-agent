import sqlite3
import threading
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from majestic.storage import connect


class ScriptTracker:
    """
    Tracks every script execution (Python/Node).
    Detects repeated scripts (3+ runs with small variations) → triggers parameterization.
    Detects successful scripts worth promoting to workspace/tools/.
    """

    REPEAT_THRESHOLD = 3

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self):
        return connect(self.db_path, wal=False)

    def _init_db(self):
        with self._lock:
            with self._get_conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS script_runs (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        lang        TEXT,
                        code_hash   TEXT,
                        code        TEXT,
                        args_json   TEXT,
                        success     INTEGER,
                        output      TEXT,
                        promoted    INTEGER DEFAULT 0,
                        created_at  TEXT
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_code_hash
                    ON script_runs(code_hash)
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS promoted_scripts (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        lang        TEXT,
                        name        TEXT,
                        path        TEXT,
                        description TEXT,
                        created_at  TEXT
                    )
                """)

    def record(
        self,
        lang: str,
        code: str,
        success: bool,
        output: str,
        args: dict = None,
    ) -> int:
        """Record a script execution. Returns the row id."""
        code_hash = self._hash(code)
        with self._lock:
            with self._get_conn() as conn:
                cur = conn.execute(
                    """INSERT INTO script_runs
                       (lang, code_hash, code, args_json, success, output, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        lang,
                        code_hash,
                        code,
                        json.dumps(args or {}),
                        1 if success else 0,
                        (output or "")[:2000],
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                return cur.lastrowid

    def should_promote(self, run_id: int) -> bool:
        """Return True if this run was successful and script is not yet promoted."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT success, promoted FROM script_runs WHERE id = ?", (run_id,)
            ).fetchone()
            return bool(row and row[0] and not row[1])

    def mark_promoted(self, run_id: int, dest_path: str, description: str = ""):
        """Mark script as promoted and record in promoted_scripts."""
        with self._lock:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT lang FROM script_runs WHERE id = ?", (run_id,)
                ).fetchone()
                lang = row[0] if row else "python"
                conn.execute(
                    "UPDATE script_runs SET promoted = 1 WHERE id = ?", (run_id,)
                )
                name = Path(dest_path).stem
                conn.execute(
                    """INSERT INTO promoted_scripts (lang, name, path, description, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (lang, name, dest_path, description, datetime.now(timezone.utc).isoformat()),
                )

    def detect_repeats(self, lang: str = None) -> list[dict]:
        """
        Find script groups that ran 3+ times.
        Uses structural similarity (normalized hash) not exact hash,
        so slight variations between runs are grouped.
        Returns list of groups ready for parameterization.
        """
        with self._get_conn() as conn:
            query = """
                SELECT code_hash, lang, COUNT(*) as run_count,
                       GROUP_CONCAT(id) as ids,
                       MAX(code) as sample_code
                FROM script_runs
                WHERE success = 1 AND promoted = 0
            """
            params = []
            if lang:
                query += " AND lang = ?"
                params.append(lang)
            query += " GROUP BY code_hash HAVING run_count >= ?"
            params.append(self.REPEAT_THRESHOLD)

            rows = conn.execute(query, params).fetchall()
            groups = []
            for row in rows:
                groups.append({
                    "code_hash": row[0],
                    "lang": row[1],
                    "run_count": row[2],
                    "ids": [int(i) for i in row[3].split(",")],
                    "sample_code": row[4],
                })
            return groups

    def get_variations(self, code_hash: str) -> list[dict]:
        """Return all runs for a given code_hash to extract argument variations."""
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT id, code, args_json, output FROM script_runs
                   WHERE code_hash = ? AND success = 1
                   ORDER BY id""",
                (code_hash,),
            ).fetchall()
            return [
                {"id": r[0], "code": r[1], "args": json.loads(r[2]), "output": r[3]}
                for r in rows
            ]

    def get_failed_scripts(self, lang: str = None) -> list[dict]:
        """Return recent failed scripts not yet fixed."""
        with self._get_conn() as conn:
            query = "SELECT id, lang, code, output FROM script_runs WHERE success = 0"
            params = []
            if lang:
                query += " AND lang = ?"
                params.append(lang)
            query += " ORDER BY id DESC LIMIT 20"
            rows = conn.execute(query, params).fetchall()
            return [{"id": r[0], "lang": r[1], "code": r[2], "error": r[3]} for r in rows]

    @staticmethod
    def _hash(code: str) -> str:
        # Normalize: strip comments, whitespace, string literals to group similar scripts
        normalized = re.sub(r'#.*', '', code)
        normalized = re.sub(r'""".*?"""', '""', normalized, flags=re.DOTALL)
        normalized = re.sub(r"'''.*?'''", "''", normalized, flags=re.DOTALL)
        normalized = re.sub(r'"[^"]*"', '"X"', normalized)
        normalized = re.sub(r"'[^']*'", "'X'", normalized)
        normalized = re.sub(r'\b\d+\b', 'N', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]
