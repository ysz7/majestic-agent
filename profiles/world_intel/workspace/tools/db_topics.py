"""
db_topics.py — Topics database manager for World Intel agent.

DB path: profiles/world_intel/data/topics.db
Usage:
    python db_topics.py add "central bank policy" --query "central bank interest rate policy"
    python db_topics.py get_all_active
    python db_topics.py get_by_name "central bank policy"
    python db_topics.py mark_checked "central bank policy"
    python db_topics.py deactivate "central bank policy"
    python db_topics.py list_all
"""

import sqlite3
import json
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

_PROFILE_ROOT = Path(__file__).parents[2]  # = profiles/world_intel/
_DB_PATH = _PROFILE_ROOT / "data" / "topics.db"


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            query TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            last_checked TEXT DEFAULT '',
            active INTEGER DEFAULT 1
        )
    """)
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rows_to_list(rows) -> list:
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def add(name: str, query: str = "") -> dict:
    """Add a new topic; returns {"saved": bool, "id": int}."""
    with _connect() as conn:
        _init_db(conn)
        cursor = conn.execute(
            "INSERT OR IGNORE INTO topics (name, query, created_at) VALUES (?, ?, ?)",
            (name, query, _now()),
        )
        conn.commit()
        inserted = cursor.rowcount > 0
        row = conn.execute("SELECT id FROM topics WHERE name = ?", (name,)).fetchone()
        result = {"saved": inserted, "id": row["id"] if row else None}
    print(json.dumps(result))
    return result


def get_all_active() -> list:
    """Return all topics with active=1."""
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            "SELECT * FROM topics WHERE active = 1 ORDER BY name ASC"
        ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


def get_by_name(name: str) -> dict:
    """Return a single topic by name."""
    with _connect() as conn:
        _init_db(conn)
        row = conn.execute("SELECT * FROM topics WHERE name = ?", (name,)).fetchone()
        result = dict(row) if row else {}
    print(json.dumps(result))
    return result


def mark_checked(name: str) -> dict:
    """Update last_checked to now for a topic."""
    with _connect() as conn:
        _init_db(conn)
        cursor = conn.execute(
            "UPDATE topics SET last_checked = ? WHERE name = ?",
            (_now(), name),
        )
        conn.commit()
        result = {"updated": cursor.rowcount > 0, "name": name}
    print(json.dumps(result))
    return result


def deactivate(name: str) -> dict:
    """Set active=0 for a topic."""
    with _connect() as conn:
        _init_db(conn)
        cursor = conn.execute(
            "UPDATE topics SET active = 0 WHERE name = ?",
            (name,),
        )
        conn.commit()
        result = {"updated": cursor.rowcount > 0, "name": name}
    print(json.dumps(result))
    return result


def list_all() -> list:
    """Return all topics including inactive."""
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            "SELECT * FROM topics ORDER BY active DESC, name ASC"
        ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Topics database manager for World Intel agent.")
    sub = parser.add_subparsers(dest="command", required=True)

    # add
    p_add = sub.add_parser("add", help="Add a new topic.")
    p_add.add_argument("name", help="Topic name (unique).")
    p_add.add_argument("--query", default="", help="Search query for this topic.")

    # get_all_active
    sub.add_parser("get_all_active", help="Return all active topics.")

    # get_by_name
    p_name = sub.add_parser("get_by_name", help="Return a single topic by name.")
    p_name.add_argument("name", help="Topic name.")

    # mark_checked
    p_check = sub.add_parser("mark_checked", help="Update last_checked to now.")
    p_check.add_argument("name", help="Topic name.")

    # deactivate
    p_deact = sub.add_parser("deactivate", help="Set active=0 for a topic.")
    p_deact.add_argument("name", help="Topic name.")

    # list_all
    sub.add_parser("list_all", help="Return all topics including inactive.")

    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "add":
        add(args.name, args.query)
    elif args.command == "get_all_active":
        get_all_active()
    elif args.command == "get_by_name":
        get_by_name(args.name)
    elif args.command == "mark_checked":
        mark_checked(args.name)
    elif args.command == "deactivate":
        deactivate(args.name)
    elif args.command == "list_all":
        list_all()
    else:
        parser.print_help()
        sys.exit(1)
