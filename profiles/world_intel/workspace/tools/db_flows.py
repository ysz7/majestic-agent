"""
db_flows.py — Capital flows database manager for World Intel agent.

DB path: profiles/world_intel/data/flows.db
Usage:
    python db_flows.py upsert '{"segment": "AI", "period": "2026-05-11", "total_amount": 500000000}'
    python db_flows.py get_by_segment AI --limit 10
    python db_flows.py get_by_period 2026-05-11
    python db_flows.py get_top_segments 2026-05-11 --n 5
    python db_flows.py get_momentum AI
    python db_flows.py get_stats
"""

import sqlite3
import json
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

_PROFILE_ROOT = Path(__file__).parents[2]  # = profiles/world_intel/
_DB_PATH = _PROFILE_ROOT / "data" / "flows.db"


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS flows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            segment TEXT NOT NULL,
            subsegment TEXT DEFAULT '',
            period TEXT NOT NULL,
            period_type TEXT DEFAULT 'daily',
            total_amount REAL DEFAULT 0.0,
            deal_count INTEGER DEFAULT 0,
            momentum TEXT DEFAULT 'stable',
            is_outlier INTEGER DEFAULT 0,
            updated_at TEXT NOT NULL,
            UNIQUE(segment, period)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_flows_period ON flows(period)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_flows_segment ON flows(segment)")
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rows_to_list(rows) -> list:
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def upsert(data: dict) -> dict:
    """INSERT OR REPLACE into flows; returns {"saved": bool}."""
    with _connect() as conn:
        _init_db(conn)
        cursor = conn.execute(
            """
            INSERT INTO flows
                (segment, subsegment, period, period_type, total_amount,
                 deal_count, momentum, is_outlier, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(segment, period) DO UPDATE SET
                subsegment   = excluded.subsegment,
                period_type  = excluded.period_type,
                total_amount = excluded.total_amount,
                deal_count   = excluded.deal_count,
                momentum     = excluded.momentum,
                is_outlier   = excluded.is_outlier,
                updated_at   = excluded.updated_at
            """,
            (
                data.get("segment", ""),
                data.get("subsegment", ""),
                data.get("period", ""),
                data.get("period_type", "daily"),
                float(data.get("total_amount", 0.0)),
                int(data.get("deal_count", 0)),
                data.get("momentum", "stable"),
                int(data.get("is_outlier", 0)),
                _now(),
            ),
        )
        conn.commit()
        result = {"saved": cursor.rowcount > 0}
    print(json.dumps(result))
    return result


def get_by_segment(segment: str, limit: int = 30) -> list:
    """Return flow records for a segment, most recent first."""
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            """
            SELECT * FROM flows
            WHERE segment = ?
            ORDER BY period DESC
            LIMIT ?
            """,
            (segment, int(limit)),
        ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


def get_by_period(period: str) -> list:
    """Return all segments for a given period (YYYY-MM-DD or YYYY-Www)."""
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            "SELECT * FROM flows WHERE period = ? ORDER BY total_amount DESC",
            (period,),
        ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


def get_top_segments(period: str, n: int = 10) -> list:
    """Return top N segments by total_amount for a given period."""
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            """
            SELECT * FROM flows
            WHERE period = ?
            ORDER BY total_amount DESC
            LIMIT ?
            """,
            (period, int(n)),
        ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


def get_momentum(segment: str) -> list:
    """Return recent periods with momentum field for a segment."""
    with _connect() as conn:
        _init_db(conn)
        rows = conn.execute(
            """
            SELECT period, momentum, total_amount, deal_count FROM flows
            WHERE segment = ?
            ORDER BY period DESC
            LIMIT 30
            """,
            (segment,),
        ).fetchall()
        result = _rows_to_list(rows)
    print(json.dumps(result))
    return result


def get_stats() -> dict:
    """Return total record count and list of distinct periods."""
    with _connect() as conn:
        _init_db(conn)
        total = conn.execute("SELECT COUNT(*) FROM flows").fetchone()[0]
        period_rows = conn.execute(
            "SELECT DISTINCT period FROM flows ORDER BY period DESC LIMIT 60"
        ).fetchall()
        result = {
            "total_records": total,
            "periods": [row["period"] for row in period_rows],
        }
    print(json.dumps(result))
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capital flows database manager for World Intel agent.")
    sub = parser.add_subparsers(dest="command", required=True)

    # upsert
    p_upsert = sub.add_parser("upsert", help="INSERT OR REPLACE a flow record.")
    p_upsert.add_argument("data", help="JSON string with flow fields.")

    # get_by_segment
    p_seg = sub.add_parser("get_by_segment", help="Return flow records for a segment.")
    p_seg.add_argument("segment", help="Segment name.")
    p_seg.add_argument("--limit", type=int, default=30, help="Max rows (default 30).")

    # get_by_period
    p_period = sub.add_parser("get_by_period", help="Return all segments for a given period.")
    p_period.add_argument("period", help="Period string (YYYY-MM-DD or YYYY-Www).")

    # get_top_segments
    p_top = sub.add_parser("get_top_segments", help="Return top N segments by total_amount.")
    p_top.add_argument("period", help="Period string.")
    p_top.add_argument("--n", type=int, default=10, help="Number of segments (default 10).")

    # get_momentum
    p_mom = sub.add_parser("get_momentum", help="Return recent periods with momentum for a segment.")
    p_mom.add_argument("segment", help="Segment name.")

    # get_stats
    sub.add_parser("get_stats", help="Return total records and distinct periods.")

    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "upsert":
        upsert(json.loads(args.data))
    elif args.command == "get_by_segment":
        get_by_segment(args.segment, args.limit)
    elif args.command == "get_by_period":
        get_by_period(args.period)
    elif args.command == "get_top_segments":
        get_top_segments(args.period, args.n)
    elif args.command == "get_momentum":
        get_momentum(args.segment)
    elif args.command == "get_stats":
        get_stats()
    else:
        parser.print_help()
        sys.exit(1)
