"""
db_pains.py — Pain points database for Pain Hunter agent.

DB path: profiles/pain_hunter/data/pains.db
Usage:
    python db_pains.py save '{"niche":"ecommerce","raw_quote":"shipping is broken","source_url":"https://reddit.com/...","source_type":"reddit","pain_summary":"slow shipping","pain_type":"missing_tool","intensity":7}'
    python db_pains.py get_unclustered "ecommerce"
    python db_pains.py get_by_niche "ecommerce" --limit 50
    python db_pains.py mark_clustered 1 2 3
    python db_pains.py stats "ecommerce"
"""

import sqlite3
import json
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parents[3] / "data" / "pains.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            niche TEXT,
            raw_quote TEXT,
            source_url TEXT,
            source_type TEXT,
            pain_summary TEXT,
            pain_type TEXT,
            intensity INTEGER,
            social_proof INTEGER DEFAULT 0,
            clustered INTEGER DEFAULT 0,
            date_found TEXT,
            created_at TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pains_niche ON pains(niche)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pains_clustered ON pains(clustered)")
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rows_to_list(rows) -> list:
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_pain(
    niche: str,
    raw_quote: str,
    source_url: str,
    source_type: str,
    pain_summary: str,
    pain_type: str,
    intensity: int,
    social_proof: int = 0,
) -> dict:
    """Insert a new pain point record."""
    now = _now()
    with _connect() as conn:
        _init_db(conn)
        cursor = conn.execute(
            """
            INSERT INTO pains
                (niche, raw_quote, source_url, source_type, pain_summary, pain_type,
                 intensity, social_proof, date_found, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                niche,
                raw_quote,
                source_url,
                source_type,
                pain_summary,
                pain_type,
                int(intensity),
                int(social_proof),
                now,
                now,
            ),
        )
        conn.commit()
        pain_id = cursor.lastrowid
        result = {"id": pain_id, "saved": True}
    print(json.dumps(result))
    return result


def get_unclustered(niche: str) -> list:
    """Return pain points for the niche that have not yet been clustered."""
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            """
            SELECT * FROM pains
            WHERE niche = ? AND clustered = 0
            ORDER BY intensity DESC, social_proof DESC
            """,
            (niche,),
        ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


def get_by_niche(niche: str, limit: int = 100) -> list:
    """Return all pain points for a niche, most intense first."""
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            """
            SELECT * FROM pains
            WHERE niche = ?
            ORDER BY intensity DESC, social_proof DESC
            LIMIT ?
            """,
            (niche, int(limit)),
        ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


def mark_clustered(pain_ids: list) -> dict:
    """Set clustered=1 for the given list of pain IDs."""
    if not pain_ids:
        result = {"error": "pain_ids list is empty.", "updated": 0}
        print(json.dumps(result))
        return result
    ids = [int(i) for i in pain_ids]
    placeholders = ",".join("?" * len(ids))
    with _connect() as conn:
        _init_db(conn)
        cursor = conn.execute(
            f"UPDATE pains SET clustered = 1 WHERE id IN ({placeholders})",
            ids,
        )
        conn.commit()
        result = {"updated": cursor.rowcount, "pain_ids": ids}
    print(json.dumps(result))
    return result


def stats(niche: str) -> dict:
    """Return count, avg_intensity, and source breakdown for a niche."""
    with _connect() as conn:
        _init_db(conn)
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                AVG(intensity) AS avg_intensity,
                SUM(social_proof) AS total_social_proof,
                SUM(CASE WHEN clustered = 0 THEN 1 ELSE 0 END) AS unclustered
            FROM pains
            WHERE niche = ?
            """,
            (niche,),
        ).fetchone()

        source_rows = conn.execute(
            """
            SELECT source_type, COUNT(*) AS cnt
            FROM pains
            WHERE niche = ?
            GROUP BY source_type
            ORDER BY cnt DESC
            """,
            (niche,),
        ).fetchall()

        type_rows = conn.execute(
            """
            SELECT pain_type, COUNT(*) AS cnt
            FROM pains
            WHERE niche = ?
            GROUP BY pain_type
            ORDER BY cnt DESC
            """,
            (niche,),
        ).fetchall()

        result = {
            "niche": niche,
            "total": row["total"] or 0,
            "avg_intensity": round(row["avg_intensity"] or 0, 2),
            "total_social_proof": row["total_social_proof"] or 0,
            "unclustered": row["unclustered"] or 0,
            "by_source": {r["source_type"]: r["cnt"] for r in source_rows},
            "by_pain_type": {r["pain_type"]: r["cnt"] for r in type_rows},
        }
    print(json.dumps(result))
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pain points database manager for Pain Hunter agent."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # save — accepts a JSON string for compact agent usage
    p_save = sub.add_parser("save", help="Insert a new pain point from a JSON string.")
    p_save.add_argument(
        "payload",
        help=(
            'JSON string with keys: niche, raw_quote, source_url, source_type, '
            'pain_summary, pain_type, intensity, [social_proof]'
        ),
    )

    # get_unclustered
    p_unc = sub.add_parser("get_unclustered", help="Return unclustered pains for a niche.")
    p_unc.add_argument("niche", help="Niche name.")

    # get_by_niche
    p_bynic = sub.add_parser("get_by_niche", help="Return all pains for a niche.")
    p_bynic.add_argument("niche", help="Niche name.")
    p_bynic.add_argument("--limit", type=int, default=100, help="Max rows (default 100).")

    # mark_clustered
    p_mark = sub.add_parser("mark_clustered", help="Mark pain IDs as clustered.")
    p_mark.add_argument("pain_ids", nargs="+", type=int, help="One or more pain IDs.")

    # stats
    p_stats = sub.add_parser("stats", help="Return stats for a niche.")
    p_stats.add_argument("niche", help="Niche name.")

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

        required = ["niche", "raw_quote", "source_url", "source_type",
                    "pain_summary", "pain_type", "intensity"]
        missing = [k for k in required if k not in payload]
        if missing:
            print(json.dumps({"error": f"Missing required fields: {missing}"}))
            sys.exit(1)

        save_pain(
            niche=payload["niche"],
            raw_quote=payload["raw_quote"],
            source_url=payload["source_url"],
            source_type=payload["source_type"],
            pain_summary=payload["pain_summary"],
            pain_type=payload["pain_type"],
            intensity=payload["intensity"],
            social_proof=payload.get("social_proof", 0),
        )
    elif args.command == "get_unclustered":
        get_unclustered(args.niche)
    elif args.command == "get_by_niche":
        get_by_niche(args.niche, args.limit)
    elif args.command == "mark_clustered":
        mark_clustered(args.pain_ids)
    elif args.command == "stats":
        stats(args.niche)
    else:
        parser.print_help()
        sys.exit(1)
