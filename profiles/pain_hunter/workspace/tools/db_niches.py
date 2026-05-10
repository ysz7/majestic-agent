"""
db_niches.py — Niche database manager for Pain Hunter agent.

DB path: profiles/pain_hunter/data/niches.db
Usage:
    python db_niches.py add "e-commerce logistics" "shipping and fulfillment pain" --priority 8
    python db_niches.py get_queue --status pending --limit 10
    python db_niches.py set_status "e-commerce logistics" in_progress
    python db_niches.py increment_pain_count "e-commerce logistics" --count 5
    python db_niches.py list_all
    python db_niches.py get_top_priority --n 3
"""

import sqlite3
import json
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parents[3] / "data" / "niches.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS niches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            description TEXT,
            status TEXT DEFAULT 'pending',
            priority INTEGER DEFAULT 5,
            pain_count INTEGER DEFAULT 0,
            last_researched TEXT,
            created_at TEXT
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

def add_niche(name: str, description: str = "", priority: int = 5) -> dict:
    """Insert a niche; silently ignore if name already exists."""
    with _connect() as conn:
        _init_db(conn)
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO niches (name, description, priority, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (name, description, int(priority), _now()),
        )
        conn.commit()
        inserted = cursor.rowcount > 0
        row = conn.execute("SELECT * FROM niches WHERE name = ?", (name,)).fetchone()
        result = {"inserted": inserted, "niche": dict(row) if row else None}
    print(json.dumps(result))
    return result


def get_queue(status: str = "pending", limit: int = 10) -> list:
    """Return niches with given status, sorted by priority desc."""
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            """
            SELECT * FROM niches
            WHERE status = ?
            ORDER BY priority DESC
            LIMIT ?
            """,
            (status, int(limit)),
        ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


def set_status(name: str, status: str) -> dict:
    """Update the status of a niche."""
    valid_statuses = {"pending", "in_progress", "done", "archived"}
    if status not in valid_statuses:
        result = {"error": f"Invalid status '{status}'. Must be one of {sorted(valid_statuses)}."}
        print(json.dumps(result))
        return result
    with _connect() as conn:
        _init_db(conn)
        updated_at = _now()
        cursor = conn.execute(
            "UPDATE niches SET status = ?, last_researched = ? WHERE name = ?",
            (status, updated_at, name),
        )
        conn.commit()
        found = cursor.rowcount > 0
        result = {"updated": found, "name": name, "status": status}
    print(json.dumps(result))
    return result


def increment_pain_count(name: str, count: int = 1) -> dict:
    """Increment pain_count for a niche by count."""
    with _connect() as conn:
        _init_db(conn)
        cursor = conn.execute(
            "UPDATE niches SET pain_count = pain_count + ?, last_researched = ? WHERE name = ?",
            (int(count), _now(), name),
        )
        conn.commit()
        found = cursor.rowcount > 0
        row = conn.execute("SELECT * FROM niches WHERE name = ?", (name,)).fetchone()
        result = {"updated": found, "niche": dict(row) if row else None}
    print(json.dumps(result))
    return result


def list_all() -> list:
    """Return all niches with full stats."""
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            "SELECT * FROM niches ORDER BY priority DESC, created_at ASC"
        ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


def get_top_priority(n: int = 3) -> list:
    """Return top N niches by priority, excluding archived."""
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            """
            SELECT * FROM niches
            WHERE status != 'archived'
            ORDER BY priority DESC
            LIMIT ?
            """,
            (int(n),),
        ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Niche database manager for Pain Hunter agent."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # add
    p_add = sub.add_parser("add", help="Insert a new niche (or ignore if exists).")
    p_add.add_argument("name", help="Niche name (unique).")
    p_add.add_argument("description", nargs="?", default="", help="Short description.")
    p_add.add_argument("--priority", type=int, default=5, help="Priority 1-10 (default 5).")

    # get_queue
    p_queue = sub.add_parser("get_queue", help="Return pending niches sorted by priority.")
    p_queue.add_argument("--status", default="pending", help="Status filter (default: pending).")
    p_queue.add_argument("--limit", type=int, default=10, help="Max rows (default 10).")

    # set_status
    p_status = sub.add_parser("set_status", help="Update the status of a niche.")
    p_status.add_argument("name", help="Niche name.")
    p_status.add_argument("status", choices=["pending", "in_progress", "done", "archived"])

    # increment_pain_count
    p_inc = sub.add_parser("increment_pain_count", help="Increment pain_count for a niche.")
    p_inc.add_argument("name", help="Niche name.")
    p_inc.add_argument("--count", type=int, default=1, help="Amount to increment (default 1).")

    # list_all
    sub.add_parser("list_all", help="Return all niches with stats.")

    # get_top_priority
    p_top = sub.add_parser("get_top_priority", help="Return top N niches by priority.")
    p_top.add_argument("--n", type=int, default=3, help="Number of niches to return (default 3).")

    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "add":
        add_niche(args.name, args.description, args.priority)
    elif args.command == "get_queue":
        get_queue(args.status, args.limit)
    elif args.command == "set_status":
        set_status(args.name, args.status)
    elif args.command == "increment_pain_count":
        increment_pain_count(args.name, args.count)
    elif args.command == "list_all":
        list_all()
    elif args.command == "get_top_priority":
        get_top_priority(args.n)
    else:
        parser.print_help()
        sys.exit(1)
