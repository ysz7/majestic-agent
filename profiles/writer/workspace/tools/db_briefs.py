"""
db_briefs.py — Content briefs database manager for Writer agent.

DB path: profiles/writer/data/briefs.db
Usage:
    python db_briefs.py save '{"format":"linkedin","topic":"AI compliance","audience":"SaaS founders","angle":"risk-first","tone":"professional","goal":"build_authority","key_points":["point1"],"sources":[],"avoid":[],"scenario":"direct"}'
    python db_briefs.py get 1
    python db_briefs.py list_all --limit 20
    python db_briefs.py link_content 1 42
"""

import sqlite3
import json
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parents[2] / "data" / "briefs.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS briefs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            format TEXT NOT NULL,
            topic TEXT,
            audience TEXT,
            angle TEXT,
            tone TEXT,
            goal TEXT,
            key_points TEXT,
            sources TEXT,
            avoid TEXT,
            scenario TEXT DEFAULT 'direct',
            delegation_source TEXT,
            created_at TEXT,
            content_id INTEGER
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_briefs_format ON briefs(format)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_briefs_scenario ON briefs(scenario)")
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rows_to_list(rows) -> list:
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_brief(
    format: str,
    topic: str = None,
    audience: str = None,
    angle: str = None,
    tone: str = None,
    goal: str = None,
    key_points=None,
    sources=None,
    avoid=None,
    scenario: str = "direct",
    delegation_source: str = None,
) -> dict:
    """Insert a new content brief record."""
    with _connect() as conn:
        _init_db(conn)
        cursor = conn.execute(
            """
            INSERT INTO briefs
                (format, topic, audience, angle, tone, goal, key_points, sources,
                 avoid, scenario, delegation_source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                format,
                topic,
                audience,
                angle,
                tone,
                goal,
                json.dumps(key_points if key_points is not None else []),
                json.dumps(sources if sources is not None else []),
                json.dumps(avoid if avoid is not None else []),
                scenario,
                delegation_source,
                _now(),
            ),
        )
        conn.commit()
        result = {"id": cursor.lastrowid, "saved": True}
    print(json.dumps(result))
    return result


def get_brief(brief_id: int) -> dict:
    """Return a single brief by id."""
    with _connect() as conn:
        _init_db(conn)
        row = conn.execute(
            "SELECT * FROM briefs WHERE id = ?",
            (int(brief_id),),
        ).fetchone()
        if row is None:
            result = {"error": f"Brief id={brief_id} not found."}
        else:
            result = dict(row)
    print(json.dumps(result))
    return result


def list_all(limit: int = 20) -> list:
    """Return recent briefs, newest first."""
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            """
            SELECT * FROM briefs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


def link_content(brief_id: int, content_id: int) -> dict:
    """Set the content_id FK on a brief record."""
    with _connect() as conn:
        _init_db(conn)
        cursor = conn.execute(
            "UPDATE briefs SET content_id = ? WHERE id = ?",
            (int(content_id), int(brief_id)),
        )
        conn.commit()
        found = cursor.rowcount > 0
        result = {"updated": found, "brief_id": brief_id, "content_id": content_id}
    print(json.dumps(result))
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Content briefs database manager for Writer agent."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # save
    p_save = sub.add_parser("save", help="Insert a new brief from a JSON string.")
    p_save.add_argument(
        "payload",
        help=(
            'JSON string with keys: format (required), topic, audience, angle, tone, '
            'goal, key_points, sources, avoid, scenario, delegation_source'
        ),
    )

    # get
    p_get = sub.add_parser("get", help="Return a brief by id.")
    p_get.add_argument("id", type=int, help="Brief id.")

    # list_all
    p_list = sub.add_parser("list_all", help="List recent briefs.")
    p_list.add_argument("--limit", type=int, default=20, help="Max rows (default 20).")

    # link_content
    p_link = sub.add_parser("link_content", help="Link a brief to a produced content record.")
    p_link.add_argument("brief_id", type=int, help="Brief id.")
    p_link.add_argument("content_id", type=int, help="Content record id.")

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

        save_brief(
            format=payload["format"],
            topic=payload.get("topic"),
            audience=payload.get("audience"),
            angle=payload.get("angle"),
            tone=payload.get("tone"),
            goal=payload.get("goal"),
            key_points=payload.get("key_points"),
            sources=payload.get("sources"),
            avoid=payload.get("avoid"),
            scenario=payload.get("scenario", "direct"),
            delegation_source=payload.get("delegation_source"),
        )
    elif args.command == "get":
        get_brief(args.id)
    elif args.command == "list_all":
        list_all(args.limit)
    elif args.command == "link_content":
        link_content(args.brief_id, args.content_id)
    else:
        parser.print_help()
        sys.exit(1)
