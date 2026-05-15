"""
majestic.cli.registry_db
~~~~~~~~~~~~~~~~~~~~~~~~
SQLite-backed agent registry — replaces data/registry.json.

All reads and writes go through this module. The on-disk format is a WAL
SQLite database at data/registry.db. Existing registry.json files are
migrated automatically on first access.

Public API (drop-in for the old JSON functions):
    load_registry()          -> dict[str, dict]
    save_entry(name, data)   -> None
    delete_entry(name)       -> None
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DB_PATH = _PROJECT_ROOT / "data" / "registry.db"
_JSON_PATH = _PROJECT_ROOT / "data" / "registry.json"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS agents (
    profile     TEXT PRIMARY KEY,
    pid         INTEGER,
    agent_name  TEXT,
    port        INTEGER,
    started_at  TEXT,
    log         TEXT,
    status      TEXT DEFAULT 'running',
    meta        TEXT DEFAULT '{}'
);
"""

_lock = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(_CREATE_TABLE)
    conn.commit()
    return conn


def _migrate_from_json(conn: sqlite3.Connection) -> None:
    """One-time import of registry.json into SQLite."""
    if not _JSON_PATH.exists():
        return
    try:
        data = json.loads(_JSON_PATH.read_text(encoding="utf-8"))
        for profile, entry in data.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO agents
                    (profile, pid, agent_name, port, started_at, log, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile,
                    entry.get("pid"),
                    entry.get("agent_name", profile),
                    entry.get("port"),
                    entry.get("started_at"),
                    entry.get("log"),
                    entry.get("status", "running"),
                ),
            )
        conn.commit()
        _JSON_PATH.rename(_JSON_PATH.with_suffix(".json.bak"))
    except Exception:
        pass


_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = _get_conn()
        _migrate_from_json(_conn)
    return _conn


def load_registry() -> dict[str, dict[str, Any]]:
    """Return all registry entries as a dict keyed by profile name."""
    with _lock:
        rows = _db().execute("SELECT * FROM agents").fetchall()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        result[row["profile"]] = {
            "pid": row["pid"],
            "profile": row["profile"],
            "agent_name": row["agent_name"],
            "port": row["port"],
            "started_at": row["started_at"],
            "log": row["log"],
            "status": row["status"],
        }
    return result


def save_entry(profile: str, data: dict[str, Any]) -> None:
    """Upsert a registry entry for *profile*."""
    with _lock:
        _db().execute(
            """
            INSERT INTO agents (profile, pid, agent_name, port, started_at, log, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(profile) DO UPDATE SET
                pid        = excluded.pid,
                agent_name = excluded.agent_name,
                port       = excluded.port,
                started_at = excluded.started_at,
                log        = excluded.log,
                status     = excluded.status
            """,
            (
                profile,
                data.get("pid"),
                data.get("agent_name", profile),
                data.get("port"),
                data.get("started_at"),
                data.get("log"),
                data.get("status", "running"),
            ),
        )
        _db().commit()


def delete_entry(profile: str) -> None:
    """Remove a registry entry for *profile*."""
    with _lock:
        _db().execute("DELETE FROM agents WHERE profile = ?", (profile,))
        _db().commit()


def get_entry(profile: str) -> dict[str, Any] | None:
    """Return a single registry entry or None if not found."""
    with _lock:
        row = _db().execute(
            "SELECT * FROM agents WHERE profile = ?", (profile,)
        ).fetchone()
    if row is None:
        return None
    return {
        "pid": row["pid"],
        "profile": row["profile"],
        "agent_name": row["agent_name"],
        "port": row["port"],
        "started_at": row["started_at"],
        "log": row["log"],
        "status": row["status"],
    }
