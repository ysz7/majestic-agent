"""
db_content.py — Content database manager for Writer agent.

DB path: profiles/writer/data/content.db
Usage:
    python db_content.py save '{"format":"blog","title":"AI for SaaS","topic":"AI compliance","audience":"SaaS founders","angle":"risk-first","word_count":1200,"file_path":"output/post.md","source_data":"{}","quality_score":7.5}'
    python db_content.py get_by_format "blog" --limit 20
    python db_content.py search "AI compliance"
    python db_content.py update_score 1 8.5
    python db_content.py stats
    python db_content.py list_all --limit 50
"""

import sqlite3
import json
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parents[2] / "data" / "content.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS content (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            format TEXT NOT NULL,
            title TEXT,
            topic TEXT,
            audience TEXT,
            angle TEXT,
            word_count INTEGER DEFAULT 0,
            file_path TEXT,
            source_data TEXT,
            quality_score REAL DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_content_format ON content(format)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_content_topic ON content(topic)")
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rows_to_list(rows) -> list:
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_content(
    format: str,
    title: str = None,
    topic: str = None,
    audience: str = None,
    angle: str = None,
    word_count: int = 0,
    file_path: str = None,
    source_data: str = "{}",
    quality_score: float = 0.0,
) -> dict:
    """Insert a new content record."""
    now = _now()
    with _connect() as conn:
        _init_db(conn)
        cursor = conn.execute(
            """
            INSERT INTO content
                (format, title, topic, audience, angle, word_count, file_path,
                 source_data, quality_score, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                format,
                title,
                topic,
                audience,
                angle,
                int(word_count),
                file_path,
                source_data,
                float(quality_score),
                now,
                now,
            ),
        )
        conn.commit()
        result = {"id": cursor.lastrowid, "saved": True}
    print(json.dumps(result))
    return result


def get_by_format(format: str, limit: int = 20) -> list:
    """Return content records filtered by format, newest first."""
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            """
            SELECT * FROM content
            WHERE format = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (format, int(limit)),
        ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


def search(query: str) -> list:
    """Full-text search across title, topic, and angle fields."""
    like = f"%{query}%"
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            """
            SELECT * FROM content
            WHERE title LIKE ? OR topic LIKE ? OR angle LIKE ?
            ORDER BY created_at DESC
            """,
            (like, like, like),
        ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


def update_score(content_id: int, quality_score: float) -> dict:
    """Update quality_score for a content record by id."""
    with _connect() as conn:
        _init_db(conn)
        cursor = conn.execute(
            "UPDATE content SET quality_score = ?, updated_at = ? WHERE id = ?",
            (float(quality_score), _now(), int(content_id)),
        )
        conn.commit()
        found = cursor.rowcount > 0
        result = {"updated": found, "id": content_id, "quality_score": quality_score}
    print(json.dumps(result))
    return result


def stats() -> dict:
    """Return count by format, average quality_score, and total word_count."""
    with _connect() as conn:
        _init_db(conn)
        totals = conn.execute(
            """
            SELECT
                COUNT(*) AS total_records,
                AVG(quality_score) AS avg_quality_score,
                SUM(word_count) AS total_word_count
            FROM content
            """
        ).fetchone()

        format_rows = conn.execute(
            """
            SELECT format, COUNT(*) AS cnt, AVG(quality_score) AS avg_score
            FROM content
            GROUP BY format
            ORDER BY cnt DESC
            """
        ).fetchall()

        result = {
            "total_records": totals["total_records"] or 0,
            "avg_quality_score": round(totals["avg_quality_score"] or 0, 2),
            "total_word_count": totals["total_word_count"] or 0,
            "by_format": [
                {
                    "format": r["format"],
                    "count": r["cnt"],
                    "avg_quality_score": round(r["avg_score"] or 0, 2),
                }
                for r in format_rows
            ],
        }
    print(json.dumps(result))
    return result


def list_all(limit: int = 50) -> list:
    """Return summary fields for all content, newest first."""
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            """
            SELECT id, format, title, word_count, quality_score, created_at
            FROM content
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Content database manager for Writer agent."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # save
    p_save = sub.add_parser("save", help="Insert a new content record from a JSON string.")
    p_save.add_argument(
        "payload",
        help=(
            'JSON string with keys: format (required), title, topic, audience, angle, '
            'word_count, file_path, source_data, quality_score'
        ),
    )

    # get_by_format
    p_fmt = sub.add_parser("get_by_format", help="Return content records by format.")
    p_fmt.add_argument("format", help="Content format (e.g. blog, linkedin).")
    p_fmt.add_argument("--limit", type=int, default=20, help="Max rows (default 20).")

    # search
    p_search = sub.add_parser("search", help="Search title, topic, and angle fields.")
    p_search.add_argument("query", help="Search string.")

    # update_score
    p_score = sub.add_parser("update_score", help="Update quality_score for a record.")
    p_score.add_argument("id", type=int, help="Content record id.")
    p_score.add_argument("quality_score", type=float, help="New score (0-10).")

    # stats
    sub.add_parser("stats", help="Return aggregate statistics.")

    # list_all
    p_list = sub.add_parser("list_all", help="List all content with summary fields.")
    p_list.add_argument("--limit", type=int, default=50, help="Max rows (default 50).")

    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "save":
        try:
            payload = json.loads(args.payload)
        except json.JSONDecodeError as exc:
            print(json.dumps({"error": f"Invalid JSON payload: {exc}"}))
            sys.exit(1)

        if "format" not in payload:
            print(json.dumps({"error": "Missing required field: format"}))
            sys.exit(1)

        save_content(
            format=payload["format"],
            title=payload.get("title"),
            topic=payload.get("topic"),
            audience=payload.get("audience"),
            angle=payload.get("angle"),
            word_count=payload.get("word_count", 0),
            file_path=payload.get("file_path"),
            source_data=payload.get("source_data", "{}"),
            quality_score=payload.get("quality_score", 0.0),
        )
    elif args.command == "get_by_format":
        get_by_format(args.format, args.limit)
    elif args.command == "search":
        search(args.query)
    elif args.command == "update_score":
        update_score(args.id, args.quality_score)
    elif args.command == "stats":
        stats()
    elif args.command == "list_all":
        list_all(args.limit)
    else:
        parser.print_help()
        sys.exit(1)
