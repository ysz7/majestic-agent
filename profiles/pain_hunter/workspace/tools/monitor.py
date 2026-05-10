"""
Continuous monitoring: scan top 3 niches, update clusters, check for opportunities.
Usage: python monitor.py [--once]
Run via cron or agent on schedule.
"""

import sys
import json
import sqlite3
import subprocess
import argparse
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

TOOLS_DIR = Path(__file__).parent
PROFILE_DIR = TOOLS_DIR.parents[2]
DATA_DIR = PROFILE_DIR / "data"
NICHES_DB = DATA_DIR / "niches.db"
CLUSTERS_DB = DATA_DIR / "clusters.db"

VALIDATION_THRESHOLD = 8.0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_top_niches(n: int = 3) -> list:
    """Load top priority niches with status pending or in_progress."""
    if not NICHES_DB.exists():
        return []
    conn = sqlite3.connect(str(NICHES_DB))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT name, status, priority FROM niches
            WHERE status IN ('pending', 'in_progress')
            ORDER BY priority DESC
            LIMIT ?
            """,
            (n,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def load_high_validation_clusters(niche: str, threshold: float = VALIDATION_THRESHOLD) -> list:
    """Load clusters that crossed the validation threshold for a niche."""
    if not CLUSTERS_DB.exists():
        return []
    conn = sqlite3.connect(str(CLUSTERS_DB))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, theme, validation_score, mention_count
            FROM clusters
            WHERE niche = ? AND validation_score >= ? AND active = 1
            ORDER BY validation_score DESC
            """,
            (niche, threshold),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def run_script(script_name: str, *args, timeout: int = 300) -> dict:
    """Run a Python script from TOOLS_DIR and return parsed JSON output."""
    cmd = [sys.executable, str(TOOLS_DIR / script_name)] + list(args)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            print(f"[monitor] {script_name} exited {result.returncode}: "
                  f"{result.stderr.strip()[:200]}", file=sys.stderr)
        # Parse the last non-empty line as JSON (scripts may print progress lines to stderr)
        stdout = result.stdout.strip()
        if stdout:
            last_line = [l for l in stdout.splitlines() if l.strip()][-1]
            try:
                return json.loads(last_line)
            except json.JSONDecodeError:
                return {"raw_output": stdout[:500]}
        return {}
    except subprocess.TimeoutExpired:
        print(f"[monitor] {script_name} timed out after {timeout}s", file=sys.stderr)
        return {"error": "timeout"}
    except Exception as exc:
        print(f"[monitor] {script_name} failed: {exc}", file=sys.stderr)
        return {"error": str(exc)}


def ideas_exist_for_cluster(cluster_id: int) -> bool:
    """Check if an idea has already been generated for a cluster."""
    ideas_db = DATA_DIR / "ideas.db"
    if not ideas_db.exists():
        return False
    conn = sqlite3.connect(str(ideas_db))
    try:
        row = conn.execute(
            "SELECT id FROM ideas WHERE cluster_id = ? LIMIT 1", (cluster_id,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Pain Hunter continuous monitor.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one monitoring cycle and exit (default: run once regardless).",
    )
    args = parser.parse_args()

    print(f"[monitor] Starting monitoring cycle at {datetime.utcnow().isoformat()}Z",
          file=sys.stderr)

    niches = load_top_niches(3)
    if not niches:
        result = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "niches_processed": 0,
            "opportunity_alerts": [],
            "message": "No pending/in_progress niches found in niches.db",
        }
        print(json.dumps(result))
        return

    opportunity_alerts = []
    niches_processed = 0

    for niche_rec in niches:
        niche = niche_rec["name"]
        print(f"\n[monitor] Processing niche: '{niche}'", file=sys.stderr)

        # Step 1: Scan (scan_hn + scan_reddit + scan_github if available)
        print(f"[monitor] Running scan_hn.py for '{niche}'...", file=sys.stderr)
        run_script("scan_hn.py", niche, timeout=120)

        print(f"[monitor] Running scan_reddit.py for '{niche}'...", file=sys.stderr)
        run_script("scan_reddit.py", niche, timeout=120)

        scan_github = TOOLS_DIR / "scan_github.py"
        if scan_github.exists():
            print(f"[monitor] Running scan_github.py for '{niche}'...", file=sys.stderr)
            run_script("scan_github.py", niche, timeout=120)

        # Step 2: Extract pain points
        print(f"[monitor] Running extract_pain.py for '{niche}'...", file=sys.stderr)
        extract_result = run_script("extract_pain.py", niche, timeout=180)
        pains_extracted = extract_result.get("pains_extracted", 0)
        print(f"[monitor] Extracted {pains_extracted} pains for '{niche}'", file=sys.stderr)

        # Step 3: Cluster pains
        print(f"[monitor] Running cluster_pains.py for '{niche}'...", file=sys.stderr)
        cluster_result = run_script("cluster_pains.py", niche, timeout=180)
        clusters_created = cluster_result.get("clusters_created", 0)
        print(f"[monitor] Created {clusters_created} clusters for '{niche}'", file=sys.stderr)

        # Step 4: Check for high-value clusters
        high_clusters = load_high_validation_clusters(niche, VALIDATION_THRESHOLD)

        new_opportunities = []
        for cluster in high_clusters:
            if not ideas_exist_for_cluster(cluster["id"]):
                print(f"[monitor] High-value cluster found: '{cluster['theme']}' "
                      f"(score={cluster['validation_score']})", file=sys.stderr)

                # Validate demand if not already done
                print(f"[monitor] Running validate_demand.py for '{niche}'...", file=sys.stderr)
                run_script("validate_demand.py", niche, timeout=120)

                # Generate idea
                print(f"[monitor] Running generate_idea.py for '{niche}' "
                      f"cluster {cluster['id']}...", file=sys.stderr)
                idea_result = run_script(
                    "generate_idea.py", niche, str(cluster["id"]), timeout=240
                )

                if idea_result.get("idea_id"):
                    alert = {
                        "niche": niche,
                        "cluster": cluster["theme"],
                        "validation_score": cluster["validation_score"],
                        "idea_id": idea_result.get("idea_id"),
                        "title": idea_result.get("title", ""),
                        "report_path": idea_result.get("report_path", ""),
                    }
                    new_opportunities.append(alert)
                    opportunity_alerts.append(alert)

        niches_processed += 1

    # Step 5: Generate daily digest
    print("\n[monitor] Running digest.py...", file=sys.stderr)
    run_script("digest.py", timeout=60)

    summary = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "niches_processed": niches_processed,
        "opportunity_alerts": opportunity_alerts,
        "alert_count": len(opportunity_alerts),
    }
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
