"""
query_content.py — Query content database.

Usage:
    python query_content.py search "AI compliance"
    python query_content.py by_format linkedin --limit 10
    python query_content.py stats
    python query_content.py recent --limit 5
    python query_content.py get 42
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Tool path
# ---------------------------------------------------------------------------

DB_CONTENT = Path(__file__).parent / "db_content.py"


# ---------------------------------------------------------------------------
# Subprocess helper
# ---------------------------------------------------------------------------

def _run_db(args: list) -> dict | list:
    """Call db_content.py with args and return parsed JSON."""
    cmd = [sys.executable, str(DB_CONTENT)] + args
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    stdout = result.stdout.strip()
    if not stdout:
        stderr = result.stderr.strip()
        return {"error": f"db_content returned no output. stderr: {stderr}"}
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {"error": f"db_content returned non-JSON: {stdout[:300]}"}


# ---------------------------------------------------------------------------
# Query handlers
# ---------------------------------------------------------------------------

def cmd_search(query: str) -> dict:
    """Full-text search across title, topic, and angle."""
    rows = _run_db(["search", query])
    if isinstance(rows, dict) and "error" in rows:
        return rows
    return {
        "query": query,
        "count": len(rows),
        "results": rows,
    }


def cmd_by_format(fmt: str, limit: int = 20) -> dict:
    """Return content records for a specific format."""
    rows = _run_db(["get_by_format", fmt, "--limit", str(limit)])
    if isinstance(rows, dict) and "error" in rows:
        return rows
    return {
        "format": fmt,
        "limit": limit,
        "count": len(rows),
        "results": rows,
    }


def cmd_stats() -> dict:
    """Return aggregate statistics formatted for readability."""
    data = _run_db(["stats"])
    if isinstance(data, dict) and "error" in data:
        return data

    # Format for human readability
    by_format_lines = []
    for entry in data.get("by_format", []):
        by_format_lines.append({
            "format": entry["format"],
            "count": entry["count"],
            "avg_quality_score": entry["avg_quality_score"],
        })

    return {
        "total_records": data.get("total_records", 0),
        "avg_quality_score": data.get("avg_quality_score", 0),
        "total_word_count": data.get("total_word_count", 0),
        "total_words_formatted": f"{data.get('total_word_count', 0):,}",
        "by_format": by_format_lines,
    }


def cmd_recent(limit: int = 5) -> dict:
    """Return most recently created content records."""
    rows = _run_db(["list_all", "--limit", str(limit)])
    if isinstance(rows, dict) and "error" in rows:
        return rows
    # list_all returns newest-first already (ORDER BY created_at DESC)
    return {
        "limit": limit,
        "count": len(rows),
        "results": rows,
    }


def cmd_get(content_id: int) -> dict:
    """
    Retrieve a single content record by id.
    db_content.py has no get-by-id command, so we use list_all with a high
    limit and filter client-side. If the DB is large, update db_content to
    add a `get <id>` command for efficiency.
    """
    # Use a large list to search — practical for typical writer DBs
    rows = _run_db(["list_all", "--limit", "10000"])
    if isinstance(rows, dict) and "error" in rows:
        return rows

    for row in rows:
        if row.get("id") == content_id:
            return {"id": content_id, "found": True, "record": row}

    return {"id": content_id, "found": False, "record": None}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Query the content database for Writer agent."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # search
    p_search = sub.add_parser("search", help="Full-text search across title, topic, angle.")
    p_search.add_argument("query", help="Search string.")

    # by_format
    p_fmt = sub.add_parser("by_format", help="List content by format.")
    p_fmt.add_argument("format", help="Content format (e.g. blog, linkedin, newsletter).")
    p_fmt.add_argument("--limit", type=int, default=20, help="Max records (default 20).")

    # stats
    sub.add_parser("stats", help="Show aggregate content statistics.")

    # recent
    p_recent = sub.add_parser("recent", help="Show most recently created content.")
    p_recent.add_argument("--limit", type=int, default=5, help="Max records (default 5).")

    # get
    p_get = sub.add_parser("get", help="Get a single content record by id.")
    p_get.add_argument("id", type=int, help="Content record id.")

    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "search":
        result = cmd_search(args.query)
    elif args.command == "by_format":
        result = cmd_by_format(args.format, args.limit)
    elif args.command == "stats":
        result = cmd_stats()
    elif args.command == "recent":
        result = cmd_recent(args.limit)
    elif args.command == "get":
        result = cmd_get(args.id)
    else:
        parser.print_help()
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))
