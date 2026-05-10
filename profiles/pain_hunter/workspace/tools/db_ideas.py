"""
db_ideas.py — Ideas database for Pain Hunter agent.

DB path: profiles/pain_hunter/data/ideas.db
Usage:
    python db_ideas.py save '{"niche":"ecommerce","cluster_id":1,"title":"ShipRadar","problem":"...","idea":"...","target_customer":"SMB store owners","solution_type":"SaaS","monetization":"$49/mo","alternatives":"ShipStation","risks":"low margin","sources":["https://..."],"output_path":"workspace/output/ecommerce_shipradar.md"}'
    python db_ideas.py update_scores 1 8.5 7.0 9.0 8.0
    python db_ideas.py get_top --min_score 6 --limit 10
    python db_ideas.py get_top --niche ecommerce
    python db_ideas.py list_all
"""

import sqlite3
import json
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parents[3] / "data" / "ideas.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ideas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            niche TEXT,
            cluster_id INTEGER,
            title TEXT,
            problem TEXT,
            idea TEXT,
            target_customer TEXT,
            solution_type TEXT,
            monetization TEXT,
            alternatives TEXT,
            risks TEXT,
            sources TEXT,
            score_desirability REAL,
            score_viability REAL,
            score_feasibility REAL,
            score_timing REAL,
            score_composite REAL,
            output_path TEXT,
            created_at TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ideas_niche ON ideas(niche)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ideas_score ON ideas(score_composite)")
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compute_composite(desirability: float, viability: float,
                        feasibility: float, timing: float) -> float:
    """Weighted composite score. Weights: D=35%, V=30%, F=20%, T=15%."""
    return round(
        desirability * 0.35
        + viability * 0.30
        + feasibility * 0.20
        + timing * 0.15,
        3,
    )


def _rows_to_list(rows, brief: bool = False) -> list:
    result = []
    for row in rows:
        d = dict(row)
        if d.get("sources") and isinstance(d["sources"], str):
            try:
                d["sources"] = json.loads(d["sources"])
            except (json.JSONDecodeError, TypeError):
                pass
        if brief:
            d = {
                k: d[k]
                for k in (
                    "id", "niche", "cluster_id", "title", "solution_type",
                    "score_composite", "score_desirability", "score_viability",
                    "score_feasibility", "score_timing", "output_path", "created_at",
                )
                if k in d
            }
        result.append(d)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_idea(
    niche: str,
    cluster_id: int,
    title: str,
    problem: str,
    idea: str,
    target_customer: str,
    solution_type: str,
    monetization: str,
    alternatives: str,
    risks: str,
    sources: list,
    output_path: str,
) -> dict:
    """Insert a new idea record and return its id."""
    sources_json = json.dumps(sources) if isinstance(sources, list) else sources
    now = _now()
    with _connect() as conn:
        _init_db(conn)
        cursor = conn.execute(
            """
            INSERT INTO ideas
                (niche, cluster_id, title, problem, idea, target_customer,
                 solution_type, monetization, alternatives, risks, sources,
                 output_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                niche,
                int(cluster_id),
                title,
                problem,
                idea,
                target_customer,
                solution_type,
                monetization,
                alternatives,
                risks,
                sources_json,
                output_path,
                now,
            ),
        )
        conn.commit()
        idea_id = cursor.lastrowid
        result = {"id": idea_id, "saved": True}
    print(json.dumps(result))
    return result


def update_scores(
    idea_id: int,
    desirability: float,
    viability: float,
    feasibility: float,
    timing: float,
) -> dict:
    """Update the four dimension scores and recompute composite."""
    composite = _compute_composite(desirability, viability, feasibility, timing)
    with _connect() as conn:
        _init_db(conn)
        cursor = conn.execute(
            """
            UPDATE ideas
            SET score_desirability = ?,
                score_viability = ?,
                score_feasibility = ?,
                score_timing = ?,
                score_composite = ?
            WHERE id = ?
            """,
            (
                float(desirability),
                float(viability),
                float(feasibility),
                float(timing),
                composite,
                int(idea_id),
            ),
        )
        conn.commit()
        found = cursor.rowcount > 0
        result = {
            "updated": found,
            "idea_id": int(idea_id),
            "score_composite": composite,
            "score_desirability": float(desirability),
            "score_viability": float(viability),
            "score_feasibility": float(feasibility),
            "score_timing": float(timing),
        }
    print(json.dumps(result))
    return result


def get_top(niche: str = None, min_score: float = 0.0, limit: int = 20) -> list:
    """Return top ideas sorted by composite score desc."""
    with _connect() as conn:
        _init_db(conn)
        if niche:
            rows = conn.execute(
                """
                SELECT * FROM ideas
                WHERE niche = ? AND (score_composite IS NULL OR score_composite >= ?)
                ORDER BY score_composite DESC NULLS LAST
                LIMIT ?
                """,
                (niche, float(min_score), int(limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM ideas
                WHERE score_composite IS NULL OR score_composite >= ?
                ORDER BY score_composite DESC NULLS LAST
                LIMIT ?
                """,
                (float(min_score), int(limit)),
            ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


def list_all() -> list:
    """Return a brief summary of all ideas."""
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            """
            SELECT * FROM ideas
            ORDER BY score_composite DESC NULLS LAST, created_at DESC
            """
        ).fetchall()
        result = _rows_to_list(rows, brief=True)
    print(json.dumps(result))
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ideas database manager for Pain Hunter agent."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # save — JSON payload
    p_save = sub.add_parser("save", help="Insert a new idea from a JSON string.")
    p_save.add_argument(
        "payload",
        help=(
            'JSON string with keys: niche, cluster_id, title, problem, idea, '
            'target_customer, solution_type, monetization, alternatives, risks, '
            'sources (list), output_path'
        ),
    )

    # update_scores
    p_scores = sub.add_parser("update_scores", help="Update scores for an idea.")
    p_scores.add_argument("idea_id", type=int, help="Idea ID.")
    p_scores.add_argument("desirability", type=float, help="Desirability score (0-10).")
    p_scores.add_argument("viability", type=float, help="Viability score (0-10).")
    p_scores.add_argument("feasibility", type=float, help="Feasibility score (0-10).")
    p_scores.add_argument("timing", type=float, help="Timing score (0-10).")

    # get_top
    p_top = sub.add_parser("get_top", help="Return top ideas by composite score.")
    p_top.add_argument("--niche", default=None, help="Filter by niche (optional).")
    p_top.add_argument("--min_score", type=float, default=0.0, help="Min composite score (default 0).")
    p_top.add_argument("--limit", type=int, default=20, help="Max rows (default 20).")

    # list_all
    sub.add_parser("list_all", help="Return a brief summary of all ideas.")

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

        required = [
            "niche", "cluster_id", "title", "problem", "idea",
            "target_customer", "solution_type", "monetization",
            "alternatives", "risks", "sources", "output_path",
        ]
        missing = [k for k in required if k not in payload]
        if missing:
            print(json.dumps({"error": f"Missing required fields: {missing}"}))
            sys.exit(1)

        save_idea(
            niche=payload["niche"],
            cluster_id=payload["cluster_id"],
            title=payload["title"],
            problem=payload["problem"],
            idea=payload["idea"],
            target_customer=payload["target_customer"],
            solution_type=payload["solution_type"],
            monetization=payload["monetization"],
            alternatives=payload["alternatives"],
            risks=payload["risks"],
            sources=payload["sources"],
            output_path=payload["output_path"],
        )
    elif args.command == "update_scores":
        update_scores(
            args.idea_id,
            args.desirability,
            args.viability,
            args.feasibility,
            args.timing,
        )
    elif args.command == "get_top":
        get_top(args.niche, args.min_score, args.limit)
    elif args.command == "list_all":
        list_all()
    else:
        parser.print_help()
        sys.exit(1)
