"""
Working memory — in-memory session store with optional SQLite persistence.

When db_path is provided, every set() call is also written to SQLite so the
key/value scratchpad survives process restarts.  On initialisation the last
session's data is loaded automatically, giving the agent continuity across
runs without requiring explicit save/load calls.

Enable via persona.yaml:
    memory:
      working_persistent: true
"""

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class WorkingMemory:
    """Ephemeral in-process memory, optionally backed by SQLite for persistence."""

    def __init__(
        self,
        db_path: str | None = None,
        session_id: str | None = None,
    ) -> None:
        self._store: dict[str, Any] = {}
        self._messages: list[dict] = []
        self._lock = threading.Lock()
        self._db: sqlite3.Connection | None = None
        self._session_id: str | None = session_id

        if db_path:
            self._init_db(db_path)

    # ------------------------------------------------------------------
    # SQLite backend
    # ------------------------------------------------------------------

    def _init_db(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            self._db = sqlite3.connect(db_path, check_same_thread=False)
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS working_kv (
                    session_id TEXT,
                    key        TEXT,
                    value_json TEXT,
                    updated_at REAL,
                    PRIMARY KEY (session_id, key)
                )
            """)
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS wm_sessions (
                    session_id  TEXT PRIMARY KEY,
                    created_at  REAL,
                    last_active REAL
                )
            """)
            self._db.commit()

            if not self._session_id:
                import uuid
                self._session_id = str(uuid.uuid4())[:8]

            now = time.time()
            self._db.execute(
                "INSERT OR IGNORE INTO wm_sessions VALUES (?, ?, ?)",
                (self._session_id, now, now),
            )
            self._db.commit()

            self._load_last_session()
        except Exception as exc:
            logger.warning("WorkingMemory: SQLite init failed, falling back to in-memory: %s", exc)
            self._db = None

    def _load_last_session(self) -> None:
        """Load persisted KV pairs for the current session into in-memory store."""
        if not self._db:
            return
        try:
            rows = self._db.execute(
                "SELECT key, value_json FROM working_kv WHERE session_id = ?",
                (self._session_id,),
            ).fetchall()
            for key, value_json in rows:
                try:
                    self._store[key] = json.loads(value_json)
                except (json.JSONDecodeError, TypeError):
                    self._store[key] = value_json
        except Exception as exc:
            logger.debug("WorkingMemory: failed to load session data: %s", exc)

    def _db_set(self, key: str, value: Any) -> None:
        if not self._db or not self._session_id:
            return
        try:
            now = time.time()
            self._db.execute(
                "INSERT OR REPLACE INTO working_kv VALUES (?, ?, ?, ?)",
                (self._session_id, key, json.dumps(value, default=str), now),
            )
            self._db.execute(
                "UPDATE wm_sessions SET last_active = ? WHERE session_id = ?",
                (now, self._session_id),
            )
            self._db.commit()
        except Exception as exc:
            logger.debug("WorkingMemory: db write failed: %s", exc)

    def _db_delete(self, key: str) -> None:
        if not self._db or not self._session_id:
            return
        try:
            self._db.execute(
                "DELETE FROM working_kv WHERE session_id = ? AND key = ?",
                (self._session_id, key),
            )
            self._db.commit()
        except Exception as exc:
            logger.debug("WorkingMemory: db delete failed: %s", exc)

    # ------------------------------------------------------------------
    # Conversation messages
    # ------------------------------------------------------------------

    def add_message(self, role: str, content: str) -> None:
        with self._lock:
            self._messages.append({"role": role, "content": content})

    def get_messages(self) -> list[dict]:
        with self._lock:
            return list(self._messages)

    def clear_messages(self) -> None:
        with self._lock:
            self._messages.clear()

    # ------------------------------------------------------------------
    # Key/value scratchpad
    # ------------------------------------------------------------------

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = value
            self._db_set(key, value)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._store.get(key, default)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)
            self._db_delete(key)

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._store.keys())

    def clear_store(self) -> None:
        with self._lock:
            self._store.clear()

    def clear_session(self) -> None:
        """Clear current session from both in-memory store and SQLite."""
        with self._lock:
            self._store.clear()
            if self._db and self._session_id:
                try:
                    self._db.execute(
                        "DELETE FROM working_kv WHERE session_id = ?",
                        (self._session_id,),
                    )
                    self._db.commit()
                except Exception as exc:
                    logger.debug("WorkingMemory: clear_session db error: %s", exc)

    def clear(self) -> None:
        """Clear messages, scratchpad (in-memory only; SQLite data persists for next session)."""
        with self._lock:
            self._messages.clear()
            self._store.clear()

    def __repr__(self) -> str:  # pragma: no cover
        backend = "sqlite" if self._db else "in-memory"
        return (
            f"<WorkingMemory messages={len(self._messages)} "
            f"store_keys={len(self._store)} backend={backend}>"
        )
