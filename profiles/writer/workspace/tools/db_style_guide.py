"""
db_style_guide.py — Style guide database manager for Writer agent.

DB path: profiles/writer/data/style_guide.db
Usage:
    python db_style_guide.py add '{"format":"linkedin","preference_type":"tone","instruction":"Use conversational contractions like dont, cant, wont","source":"user"}'
    python db_style_guide.py get_for_format "linkedin"
    python db_style_guide.py get_global
    python db_style_guide.py deactivate 3
    python db_style_guide.py list_all
"""

import sqlite3
import json
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parents[2] / "data" / "style_guide.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS style_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            format TEXT NOT NULL,
            preference_type TEXT NOT NULL,
            instruction TEXT NOT NULL,
            example_before TEXT,
            example_after TEXT,
            source TEXT DEFAULT 'user',
            weight REAL DEFAULT 1.0,
            active INTEGER DEFAULT 1,
            created_at TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_style_format ON style_entries(format)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_style_active ON style_entries(active)")
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rows_to_list(rows) -> list:
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def add_entry(
    format: str,
    preference_type: str,
    instruction: str,
    example_before: str = None,
    example_after: str = None,
    source: str = "user",
    weight: float = 1.0,
) -> dict:
    """Insert a new style guide entry."""
    with _connect() as conn:
        _init_db(conn)
        cursor = conn.execute(
            """
            INSERT INTO style_entries
                (format, preference_type, instruction, example_before, example_after,
                 source, weight, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                format,
                preference_type,
                instruction,
                example_before,
                example_after,
                source,
                float(weight),
                _now(),
            ),
        )
        conn.commit()
        result = {"id": cursor.lastrowid, "saved": True}
    print(json.dumps(result))
    return result


def get_for_format(format: str) -> list:
    """Return all active entries for a specific format plus global entries, weight desc."""
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            """
            SELECT * FROM style_entries
            WHERE active = 1 AND (format = ? OR format = 'global')
            ORDER BY weight DESC, created_at ASC
            """,
            (format,),
        ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


def get_global() -> list:
    """Return all active global entries (format='global'), weight desc."""
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            """
            SELECT * FROM style_entries
            WHERE active = 1 AND format = 'global'
            ORDER BY weight DESC, created_at ASC
            """
        ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


def deactivate(entry_id: int) -> dict:
    """Set active=0 for a style entry by id."""
    with _connect() as conn:
        _init_db(conn)
        cursor = conn.execute(
            "UPDATE style_entries SET active = 0 WHERE id = ?",
            (int(entry_id),),
        )
        conn.commit()
        found = cursor.rowcount > 0
        result = {"deactivated": found, "id": entry_id}
    print(json.dumps(result))
    return result


def list_all() -> list:
    """Return all style entries regardless of active status."""
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            """
            SELECT * FROM style_entries
            ORDER BY format ASC, weight DESC, created_at ASC
            """
        ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Style guide database manager for Writer agent."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # add
    p_add = sub.add_parser("add", help="Insert a new style entry from a JSON string.")
    p_add.add_argument(
        "payload",
        help=(
            'JSON string with keys: format (required), preference_type (required), '
            'instruction (required), example_before, example_after, source, weight'
        ),
    )

    # get_for_format
    p_fmt = sub.add_parser("get_for_format", help="Return active entries for a format + global.")
    p_fmt.add_argument("format", help="Content format (e.g. linkedin, blog, global).")

    # get_global
    sub.add_parser("get_global", help="Return all active global style entries.")

    # deactivate
    p_deact = sub.add_parser("deactivate", help="Deactivate a style entry by id.")
    p_deact.add_argument("id", type=int, help="Style entry id.")

    # list_all
    sub.add_parser("list_all", help="List all style entries (active and inactive).")

    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "add":
        try:
            payload = json.loads(args.payload)
        except json.JSONDecodeError as exc:
            print(json.dumps({"error": f"Invalid JSON payload: {exc}"}))
            sys.exit(1)

        required = ["format", "preference_type", "instruction"]
        missing = [k for k in required if k not in payload]
        if missing:
            print(json.dumps({"error": f"Missing required fields: {missing}"}))
            sys.exit(1)

        add_entry(
            format=payload["format"],
            preference_type=payload["preference_type"],
            instruction=payload["instruction"],
            example_before=payload.get("example_before"),
            example_after=payload.get("example_after"),
            source=payload.get("source", "user"),
            weight=payload.get("weight", 1.0),
        )
    elif args.command == "get_for_format":
        get_for_format(args.format)
    elif args.command == "get_global":
        get_global()
    elif args.command == "deactivate":
        deactivate(args.id)
    elif args.command == "list_all":
        list_all()
    else:
        parser.print_help()
        sys.exit(1)
