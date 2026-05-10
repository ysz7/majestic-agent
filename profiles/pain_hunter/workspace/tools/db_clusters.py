"""
db_clusters.py — Clusters database for Pain Hunter agent.

DB path: profiles/pain_hunter/data/clusters.db
Usage:
    python db_clusters.py save '{"niche":"ecommerce","theme":"slow shipping","pain_ids":[1,2,3],"avg_intensity":7.5,"total_social_proof":320,"source_types":["reddit","hackernews"]}'
    python db_clusters.py update_validation 1 8.5 "3 reddit threads, 2 HN posts confirm"
    python db_clusters.py get_top "ecommerce" --min_mentions 3 --limit 10
    python db_clusters.py get_all "ecommerce"
    python db_clusters.py get_high_priority --min_validation 7
"""

import sqlite3
import json
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parents[3] / "data" / "clusters.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clusters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            niche TEXT,
            theme TEXT,
            pain_ids TEXT,
            mention_count INTEGER,
            avg_intensity REAL,
            total_social_proof INTEGER,
            source_types TEXT,
            validation_score REAL DEFAULT 0,
            validation_evidence TEXT,
            first_seen TEXT,
            last_updated TEXT,
            active INTEGER DEFAULT 1
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_clusters_niche ON clusters(niche)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_clusters_active ON clusters(active)")
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rows_to_list(rows) -> list:
    result = []
    for row in rows:
        d = dict(row)
        # Deserialize JSON-stored fields for convenience
        for field in ("pain_ids", "source_types"):
            if d.get(field) and isinstance(d[field], str):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        result.append(d)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_cluster(
    niche: str,
    theme: str,
    pain_ids: list,
    avg_intensity: float,
    total_social_proof: int,
    source_types: list,
) -> dict:
    """Insert a new cluster record."""
    now = _now()
    mention_count = len(pain_ids)
    pain_ids_json = json.dumps(pain_ids)
    source_types_json = json.dumps(source_types)
    with _connect() as conn:
        _init_db(conn)
        cursor = conn.execute(
            """
            INSERT INTO clusters
                (niche, theme, pain_ids, mention_count, avg_intensity,
                 total_social_proof, source_types, first_seen, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                niche,
                theme,
                pain_ids_json,
                mention_count,
                float(avg_intensity),
                int(total_social_proof),
                source_types_json,
                now,
                now,
            ),
        )
        conn.commit()
        cluster_id = cursor.lastrowid
        result = {"id": cluster_id, "saved": True, "mention_count": mention_count}
    print(json.dumps(result))
    return result


def update_validation(cluster_id: int, score: float, evidence: str) -> dict:
    """Update validation_score and validation_evidence for a cluster."""
    with _connect() as conn:
        _init_db(conn)
        cursor = conn.execute(
            """
            UPDATE clusters
            SET validation_score = ?, validation_evidence = ?, last_updated = ?
            WHERE id = ?
            """,
            (float(score), evidence, _now(), int(cluster_id)),
        )
        conn.commit()
        found = cursor.rowcount > 0
        result = {
            "updated": found,
            "cluster_id": int(cluster_id),
            "validation_score": float(score),
        }
    print(json.dumps(result))
    return result


def get_top(niche: str, min_mentions: int = 3, limit: int = 10) -> list:
    """Return top clusters for a niche, sorted by validation_score desc."""
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            """
            SELECT * FROM clusters
            WHERE niche = ? AND mention_count >= ? AND active = 1
            ORDER BY validation_score DESC, mention_count DESC
            LIMIT ?
            """,
            (niche, int(min_mentions), int(limit)),
        ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


def get_all(niche: str) -> list:
    """Return all clusters for a niche."""
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            """
            SELECT * FROM clusters
            WHERE niche = ?
            ORDER BY validation_score DESC, mention_count DESC
            """,
            (niche,),
        ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


def get_high_priority(min_validation: float = 7.0) -> list:
    """Return active clusters with validation_score >= min_validation, ready for idea gen."""
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            """
            SELECT * FROM clusters
            WHERE validation_score >= ? AND active = 1
            ORDER BY validation_score DESC, total_social_proof DESC
            """,
            (float(min_validation),),
        ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Clusters database manager for Pain Hunter agent."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # save — JSON payload
    p_save = sub.add_parser("save", help="Insert a new cluster from a JSON string.")
    p_save.add_argument(
        "payload",
        help=(
            'JSON string with keys: niche, theme, pain_ids (list), '
            'avg_intensity, total_social_proof, source_types (list)'
        ),
    )

    # update_validation
    p_val = sub.add_parser("update_validation", help="Update validation score/evidence.")
    p_val.add_argument("cluster_id", type=int, help="Cluster ID.")
    p_val.add_argument("score", type=float, help="Validation score (0-10).")
    p_val.add_argument("evidence", help="Free-text validation evidence.")

    # get_top
    p_top = sub.add_parser("get_top", help="Return top clusters for a niche.")
    p_top.add_argument("niche", help="Niche name.")
    p_top.add_argument("--min_mentions", type=int, default=3, help="Min mention count (default 3).")
    p_top.add_argument("--limit", type=int, default=10, help="Max rows (default 10).")

    # get_all
    p_all = sub.add_parser("get_all", help="Return all clusters for a niche.")
    p_all.add_argument("niche", help="Niche name.")

    # get_high_priority
    p_hp = sub.add_parser("get_high_priority", help="Return high-priority clusters.")
    p_hp.add_argument(
        "--min_validation", type=float, default=7.0,
        help="Minimum validation score (default 7.0)."
    )

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

        required = ["niche", "theme", "pain_ids", "avg_intensity",
                    "total_social_proof", "source_types"]
        missing = [k for k in required if k not in payload]
        if missing:
            print(json.dumps({"error": f"Missing required fields: {missing}"}))
            sys.exit(1)

        save_cluster(
            niche=payload["niche"],
            theme=payload["theme"],
            pain_ids=payload["pain_ids"],
            avg_intensity=payload["avg_intensity"],
            total_social_proof=payload["total_social_proof"],
            source_types=payload["source_types"],
        )
    elif args.command == "update_validation":
        update_validation(args.cluster_id, args.score, args.evidence)
    elif args.command == "get_top":
        get_top(args.niche, args.min_mentions, args.limit)
    elif args.command == "get_all":
        get_all(args.niche)
    elif args.command == "get_high_priority":
        get_high_priority(args.min_validation)
    else:
        parser.print_help()
        sys.exit(1)
