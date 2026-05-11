"""
db_sources.py — Sources database manager for World Intel agent.

DB path: profiles/world_intel/data/sources.db
Usage:
    python db_sources.py upsert '{"name": "Reuters", "domain": "reuters.com", "tier": 1}'
    python db_sources.py get_by_domain reuters.com
    python db_sources.py increment_count reuters.com --count 5
    python db_sources.py update_reliability reuters.com 0.95
    python db_sources.py list_all
"""

import sqlite3
import json
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

_PROFILE_ROOT = Path(__file__).parents[2]  # = profiles/world_intel/
_DB_PATH = _PROFILE_ROOT / "data" / "sources.db"


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            domain TEXT NOT NULL UNIQUE,
            tier INTEGER DEFAULT 2,
            category TEXT DEFAULT 'general',
            reliability_score REAL DEFAULT 0.8,
            last_checked TEXT DEFAULT '',
            total_articles INTEGER DEFAULT 0
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

def upsert(data: dict) -> dict:
    """INSERT OR IGNORE then UPDATE source record; returns {"saved": bool}."""
    with _connect() as conn:
        _init_db(conn)
        conn.execute(
            """
            INSERT OR IGNORE INTO sources (name, domain, tier, category, reliability_score)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                data.get("name", ""),
                data.get("domain", ""),
                int(data.get("tier", 2)),
                data.get("category", "general"),
                float(data.get("reliability_score", 0.8)),
            ),
        )
        cursor = conn.execute(
            """
            UPDATE sources SET
                name              = ?,
                tier              = ?,
                category          = ?,
                reliability_score = ?
            WHERE domain = ?
            """,
            (
                data.get("name", ""),
                int(data.get("tier", 2)),
                data.get("category", "general"),
                float(data.get("reliability_score", 0.8)),
                data.get("domain", ""),
            ),
        )
        conn.commit()
        result = {"saved": cursor.rowcount > 0}
    print(json.dumps(result))
    return result


def get_by_domain(domain: str) -> dict:
    """Return a single source row by domain."""
    with _connect() as conn:
        _init_db(conn)
        row = conn.execute(
            "SELECT * FROM sources WHERE domain = ?", (domain,)
        ).fetchone()
        result = dict(row) if row else {}
    print(json.dumps(result))
    return result


def increment_count(domain: str, count: int = 1) -> dict:
    """Increment total_articles and update last_checked for a source."""
    with _connect() as conn:
        _init_db(conn)
        cursor = conn.execute(
            """
            UPDATE sources
            SET total_articles = total_articles + ?,
                last_checked = ?
            WHERE domain = ?
            """,
            (int(count), _now(), domain),
        )
        conn.commit()
        result = {"updated": cursor.rowcount > 0, "domain": domain}
    print(json.dumps(result))
    return result


def update_reliability(domain: str, score: float) -> dict:
    """Set reliability_score for a source."""
    with _connect() as conn:
        _init_db(conn)
        cursor = conn.execute(
            "UPDATE sources SET reliability_score = ? WHERE domain = ?",
            (float(score), domain),
        )
        conn.commit()
        result = {"updated": cursor.rowcount > 0, "domain": domain, "reliability_score": float(score)}
    print(json.dumps(result))
    return result


def list_all() -> list:
    """Return all sources sorted by tier ASC, reliability_score DESC."""
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            "SELECT * FROM sources ORDER BY tier ASC, reliability_score DESC"
        ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sources database manager for World Intel agent.")
    sub = parser.add_subparsers(dest="command", required=True)

    # upsert
    p_upsert = sub.add_parser("upsert", help="INSERT OR IGNORE then UPDATE a source.")
    p_upsert.add_argument("data", help="JSON string with source fields.")

    # get_by_domain
    p_domain = sub.add_parser("get_by_domain", help="Return a source by domain.")
    p_domain.add_argument("domain", help="Domain (e.g. reuters.com).")

    # increment_count
    p_inc = sub.add_parser("increment_count", help="Increment total_articles and update last_checked.")
    p_inc.add_argument("domain", help="Domain.")
    p_inc.add_argument("--count", type=int, default=1, help="Amount to add (default 1).")

    # update_reliability
    p_rel = sub.add_parser("update_reliability", help="Set reliability_score for a source.")
    p_rel.add_argument("domain", help="Domain.")
    p_rel.add_argument("score", type=float, help="New reliability score (0.0–1.0).")

    # list_all
    sub.add_parser("list_all", help="Return all sources sorted by tier and reliability.")

    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "upsert":
        upsert(json.loads(args.data))
    elif args.command == "get_by_domain":
        get_by_domain(args.domain)
    elif args.command == "increment_count":
        increment_count(args.domain, args.count)
    elif args.command == "update_reliability":
        update_reliability(args.domain, args.score)
    elif args.command == "list_all":
        list_all()
    else:
        parser.print_help()
        sys.exit(1)
