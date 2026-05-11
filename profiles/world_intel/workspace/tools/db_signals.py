"""
db_signals.py — Signals database manager for World Intel agent.

DB path: profiles/world_intel/data/signals.db
Usage:
    python db_signals.py save '{"type": "funding_round", "news_id": "abc123", "data_json": "{}"}'
    python db_signals.py get <id>
    python db_signals.py get_by_type funding_round --date 2026-05-11 --limit 20
    python db_signals.py get_by_news_id <news_id>
    python db_signals.py get_by_period 2026-05-01 --period_end 2026-05-11
    python db_signals.py get_funding_signals --date 2026-05-11 --limit 20
    python db_signals.py get_policy_signals --limit 10
    python db_signals.py get_stats
"""

import sqlite3
import json
import sys
import uuid
import argparse
from datetime import datetime, timezone
from pathlib import Path

_PROFILE_ROOT = Path(__file__).parents[2]  # = profiles/world_intel/
_DB_PATH = _PROFILE_ROOT / "data" / "signals.db"


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            news_id TEXT NOT NULL,
            data_json TEXT NOT NULL DEFAULT '{}',
            significance TEXT DEFAULT 'medium',
            extracted_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_type ON signals(type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_news_id ON signals(news_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_date ON signals(extracted_at)")
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rows_to_list(rows) -> list:
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save(data: dict) -> dict:
    """Insert a signal; id=uuid4 if not provided."""
    with _connect() as conn:
        _init_db(conn)
        item_id = data.get("id") or uuid.uuid4().hex
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO signals
                (id, type, news_id, data_json, significance, extracted_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                data.get("type", ""),
                data.get("news_id", ""),
                data.get("data_json", "{}"),
                data.get("significance", "medium"),
                data.get("extracted_at", _now()),
            ),
        )
        conn.commit()
        result = {"saved": cursor.rowcount > 0, "id": item_id}
    print(json.dumps(result))
    return result


def get(item_id: str) -> dict:
    """Return a single signal row as JSON dict."""
    with _connect() as conn:
        _init_db(conn)
        row = conn.execute("SELECT * FROM signals WHERE id = ?", (item_id,)).fetchone()
        result = dict(row) if row else {}
    print(json.dumps(result))
    return result


def get_by_type(signal_type: str, date: str = "", limit: int = 50) -> list:
    """Return signals filtered by type, optionally by date prefix."""
    with _connect() as conn:
        _init_db(conn)
        if date:
            rows = conn.execute(
                """
                SELECT * FROM signals
                WHERE type = ? AND extracted_at LIKE ?
                ORDER BY extracted_at DESC
                LIMIT ?
                """,
                (signal_type, f"{date}%", int(limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM signals
                WHERE type = ?
                ORDER BY extracted_at DESC
                LIMIT ?
                """,
                (signal_type, int(limit)),
            ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


def get_by_news_id(news_id: str) -> list:
    """Return all signals linked to a given news item."""
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            "SELECT * FROM signals WHERE news_id = ? ORDER BY extracted_at DESC",
            (news_id,),
        ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


def get_by_period(date: str, period_end: str = "") -> list:
    """Return signals within a date range based on extracted_at."""
    with _connect() as conn:
        _init_db(conn)
        if period_end:
            rows = conn.execute(
                """
                SELECT * FROM signals
                WHERE extracted_at >= ? AND extracted_at <= ?
                ORDER BY extracted_at DESC
                """,
                (date, period_end + "T23:59:59"),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM signals
                WHERE extracted_at LIKE ?
                ORDER BY extracted_at DESC
                """,
                (f"{date}%",),
            ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


def get_funding_signals(date: str = "", limit: int = 50) -> list:
    """Shortcut for signals of type=funding_round."""
    return get_by_type("funding_round", date=date, limit=limit)


def get_policy_signals(date: str = "", limit: int = 50) -> list:
    """Shortcut for signals of type=policy_change."""
    return get_by_type("policy_change", date=date, limit=limit)


def get_stats() -> dict:
    """Return total count and breakdown by type."""
    with _connect() as conn:
        _init_db(conn)
        total = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
        type_rows = conn.execute(
            "SELECT type, COUNT(*) AS cnt FROM signals GROUP BY type ORDER BY cnt DESC"
        ).fetchall()
        result = {
            "total": total,
            "by_type": {row["type"]: row["cnt"] for row in type_rows},
        }
    print(json.dumps(result))
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Signals database manager for World Intel agent.")
    sub = parser.add_subparsers(dest="command", required=True)

    # save
    p_save = sub.add_parser("save", help="Insert a signal (id=uuid4 if not provided).")
    p_save.add_argument("data", help="JSON string with signal fields.")

    # get
    p_get = sub.add_parser("get", help="Return a single signal row.")
    p_get.add_argument("id", help="Signal ID.")

    # get_by_type
    p_type = sub.add_parser("get_by_type", help="Return signals filtered by type.")
    p_type.add_argument("type", help="Signal type (funding_round/policy_change/market_move).")
    p_type.add_argument("--date", default="", help="Filter by date prefix (YYYY-MM-DD).")
    p_type.add_argument("--limit", type=int, default=50, help="Max rows (default 50).")

    # get_by_news_id
    p_news = sub.add_parser("get_by_news_id", help="Return all signals for a news item.")
    p_news.add_argument("news_id", help="News item ID.")

    # get_by_period
    p_period = sub.add_parser("get_by_period", help="Return signals within a date range.")
    p_period.add_argument("date", help="Start date (YYYY-MM-DD).")
    p_period.add_argument("--period_end", default="", help="End date (YYYY-MM-DD).")

    # get_funding_signals
    p_fund = sub.add_parser("get_funding_signals", help="Shortcut for type=funding_round.")
    p_fund.add_argument("--date", default="", help="Filter by date (YYYY-MM-DD).")
    p_fund.add_argument("--limit", type=int, default=50, help="Max rows (default 50).")

    # get_policy_signals
    p_policy = sub.add_parser("get_policy_signals", help="Shortcut for type=policy_change.")
    p_policy.add_argument("--date", default="", help="Filter by date (YYYY-MM-DD).")
    p_policy.add_argument("--limit", type=int, default=50, help="Max rows (default 50).")

    # get_stats
    sub.add_parser("get_stats", help="Return total and breakdown by type.")

    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "save":
        save(json.loads(args.data))
    elif args.command == "get":
        get(args.id)
    elif args.command == "get_by_type":
        get_by_type(args.type, args.date, args.limit)
    elif args.command == "get_by_news_id":
        get_by_news_id(args.news_id)
    elif args.command == "get_by_period":
        get_by_period(args.date, args.period_end)
    elif args.command == "get_funding_signals":
        get_funding_signals(args.date, args.limit)
    elif args.command == "get_policy_signals":
        get_policy_signals(args.date, args.limit)
    elif args.command == "get_stats":
        get_stats()
    else:
        parser.print_help()
        sys.exit(1)
