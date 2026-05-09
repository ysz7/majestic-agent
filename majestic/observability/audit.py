import sqlite3, json, threading
from datetime import datetime

class AuditLog:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    event_type TEXT,
                    agent TEXT,
                    data TEXT
                )
            """)

    def log(self, event_type: str, agent: str, data: dict):
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO audit_log (timestamp, event_type, agent, data) VALUES (?, ?, ?, ?)",
                    (datetime.utcnow().isoformat(), event_type, agent, json.dumps(data))
                )

    def get_recent(self, limit: int = 50) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT timestamp, event_type, agent, data FROM audit_log ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [{"timestamp": r[0], "event_type": r[1], "agent": r[2], "data": json.loads(r[3])} for r in rows]
