"""
db_news.py — News database manager for World Intel agent.

DB path: profiles/world_intel/data/news.db
Usage:
    python db_news.py save '{"headline": "...", "source": "...", "source_url": "..."}'
    python db_news.py get <id>
    python db_news.py get_by_category politics --date 2026-05-11 --limit 20
    python db_news.py get_by_date 2026-05-11
    python db_news.py search "central bank"
    python db_news.py list_recent --limit 10
    python db_news.py get_stats
    python db_news.py exists_url "https://example.com/article"
"""

import sqlite3
import json
import sys
import uuid
import argparse
from datetime import datetime, timezone
from pathlib import Path

_PROFILE_ROOT = Path(__file__).parents[2]  # = profiles/world_intel/
_DB_PATH = _PROFILE_ROOT / "data" / "news.db"


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id TEXT PRIMARY KEY,
            headline TEXT NOT NULL,
            summary TEXT DEFAULT '',
            source TEXT DEFAULT '',
            source_url TEXT DEFAULT '',
            category TEXT DEFAULT 'other',
            subcategory TEXT DEFAULT '',
            region TEXT DEFAULT 'global',
            date TEXT DEFAULT '',
            collected_at TEXT NOT NULL,
            importance INTEGER DEFAULT 3
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_news_category ON news(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_news_date ON news(date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_news_importance ON news(importance DESC)")
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rows_to_list(rows) -> list:
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save(data: dict) -> dict:
    """Insert a news item; id=uuid4 if not provided."""
    with _connect() as conn:
        _init_db(conn)
        item_id = data.get("id") or uuid.uuid4().hex
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO news
                (id, headline, summary, source, source_url, category, subcategory,
                 region, date, collected_at, importance)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                data.get("headline", ""),
                data.get("summary", ""),
                data.get("source", ""),
                data.get("source_url", ""),
                data.get("category", "other"),
                data.get("subcategory", ""),
                data.get("region", "global"),
                data.get("date", ""),
                data.get("collected_at", _now()),
                int(data.get("importance", 3)),
            ),
        )
        conn.commit()
        result = {"saved": cursor.rowcount > 0, "id": item_id}
    print(json.dumps(result))
    return result


def get(item_id: str) -> dict:
    """Return a single news row as JSON dict."""
    with _connect() as conn:
        _init_db(conn)
        row = conn.execute("SELECT * FROM news WHERE id = ?", (item_id,)).fetchone()
        result = dict(row) if row else {}
    print(json.dumps(result))
    return result


def get_by_category(category: str, date: str = "", limit: int = 50) -> list:
    """Return news items filtered by category, optionally by date."""
    with _connect() as conn:
        _init_db(conn)
        if date:
            rows = conn.execute(
                """
                SELECT * FROM news
                WHERE category = ? AND date = ?
                ORDER BY importance DESC, collected_at DESC
                LIMIT ?
                """,
                (category, date, int(limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM news
                WHERE category = ?
                ORDER BY importance DESC, collected_at DESC
                LIMIT ?
                """,
                (category, int(limit)),
            ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


def get_by_date(date: str) -> list:
    """Return all news items for a given YYYY-MM-DD date."""
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            "SELECT * FROM news WHERE date = ? ORDER BY importance DESC, collected_at DESC",
            (date,),
        ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


def search(query: str) -> list:
    """LIKE search on headline and summary fields."""
    with _connect() as conn:
        _init_db(conn)
        pattern = f"%{query}%"
        rows = conn.execute(
            """
            SELECT * FROM news
            WHERE headline LIKE ? OR summary LIKE ?
            ORDER BY importance DESC, collected_at DESC
            """,
            (pattern, pattern),
        ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


def list_recent(limit: int = 20) -> list:
    """Return most recent news items by collected_at."""
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            "SELECT * FROM news ORDER BY collected_at DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


def get_stats() -> dict:
    """Return total count and breakdowns by category and date."""
    with _connect() as conn:
        _init_db(conn)
        total = conn.execute("SELECT COUNT(*) FROM news").fetchone()[0]
        cat_rows = conn.execute(
            "SELECT category, COUNT(*) AS cnt FROM news GROUP BY category ORDER BY cnt DESC"
        ).fetchall()
        date_rows = conn.execute(
            "SELECT date, COUNT(*) AS cnt FROM news WHERE date != '' GROUP BY date ORDER BY date DESC LIMIT 30"
        ).fetchall()
        result = {
            "total": total,
            "by_category": {row["category"]: row["cnt"] for row in cat_rows},
            "by_date": {row["date"]: row["cnt"] for row in date_rows},
        }
    print(json.dumps(result))
    return result


def exists_url(url: str) -> dict:
    """Check if a URL already exists in the DB — for dedup."""
    with _connect() as conn:
        _init_db(conn)
        row = conn.execute(
            "SELECT id FROM news WHERE source_url = ? LIMIT 1", (url,)
        ).fetchone()
        result = {"exists": row is not None}
    print(json.dumps(result))
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="News database manager for World Intel agent.")
    sub = parser.add_subparsers(dest="command", required=True)

    # save
    p_save = sub.add_parser("save", help="Insert a news item (id=uuid4 if not provided).")
    p_save.add_argument("data", help="JSON string with news fields.")

    # get
    p_get = sub.add_parser("get", help="Return a single news row.")
    p_get.add_argument("id", help="News item ID.")

    # get_by_category
    p_cat = sub.add_parser("get_by_category", help="Return news filtered by category.")
    p_cat.add_argument("category", help="Category name.")
    p_cat.add_argument("--date", default="", help="Filter by date (YYYY-MM-DD).")
    p_cat.add_argument("--limit", type=int, default=50, help="Max rows (default 50).")

    # get_by_date
    p_date = sub.add_parser("get_by_date", help="Return all news for a given date.")
    p_date.add_argument("date", help="Date string (YYYY-MM-DD).")

    # search
    p_search = sub.add_parser("search", help="LIKE search on headline and summary.")
    p_search.add_argument("query", help="Search query string.")

    # list_recent
    p_recent = sub.add_parser("list_recent", help="Return most recent news items.")
    p_recent.add_argument("--limit", type=int, default=20, help="Max rows (default 20).")

    # get_stats
    sub.add_parser("get_stats", help="Return totals and breakdowns.")

    # exists_url
    p_url = sub.add_parser("exists_url", help="Check if a URL already exists (dedup).")
    p_url.add_argument("url", help="Source URL to check.")

    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "save":
        save(json.loads(args.data))
    elif args.command == "get":
        get(args.id)
    elif args.command == "get_by_category":
        get_by_category(args.category, args.date, args.limit)
    elif args.command == "get_by_date":
        get_by_date(args.date)
    elif args.command == "search":
        search(args.query)
    elif args.command == "list_recent":
        list_recent(args.limit)
    elif args.command == "get_stats":
        get_stats()
    elif args.command == "exists_url":
        exists_url(args.url)
    else:
        parser.print_help()
        sys.exit(1)
