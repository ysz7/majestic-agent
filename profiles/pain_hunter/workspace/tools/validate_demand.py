"""
Validate demand for top clusters via web search signals.
Usage: python validate_demand.py "e-commerce logistics"
Updates validation_score in data/clusters.db
"""

import sys
import json
import sqlite3
import subprocess
import time
from pathlib import Path
from datetime import datetime
from urllib.parse import quote_plus
import httpx

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

TOOLS_DIR = Path(__file__).parent
PROFILE_DIR = TOOLS_DIR.parents[2]
DATA_DIR = PROFILE_DIR / "data"
CLUSTERS_DB = DATA_DIR / "clusters.db"

DUCKDUCKGO_API = "https://api.duckduckgo.com/"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_top_clusters(niche: str, limit: int = 10) -> list:
    """Load top clusters for a niche directly from clusters.db."""
    if not CLUSTERS_DB.exists():
        return []
    conn = sqlite3.connect(str(CLUSTERS_DB))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, niche, theme, mention_count, avg_intensity,
                   total_social_proof, source_types, validation_score
            FROM clusters
            WHERE niche = ? AND mention_count >= 3 AND active = 1
            ORDER BY avg_intensity DESC, total_social_proof DESC
            LIMIT ?
            """,
            (niche, limit),
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            if d.get("source_types") and isinstance(d["source_types"], str):
                try:
                    d["source_types"] = json.loads(d["source_types"])
                except (json.JSONDecodeError, TypeError):
                    pass
            result.append(d)
        return result
    finally:
        conn.close()


def ddg_search(query: str) -> dict:
    """Call DuckDuckGo Instant Answer API. Returns parsed JSON or empty dict."""
    params = {
        "q": query,
        "format": "json",
        "no_html": "1",
        "skip_disambig": "1",
    }
    try:
        resp = httpx.get(DUCKDUCKGO_API, params=params, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        print(f"[validate_demand] DDG search error for '{query}': {exc}", file=sys.stderr)
        return {}


def count_results(data: dict) -> int:
    """Estimate result count from DDG response."""
    related = data.get("RelatedTopics", [])
    results = data.get("Results", [])
    total = len(related) + len(results)
    # Abstract text is a strong signal too
    if data.get("AbstractText"):
        total += 3
    return total


def score_cluster(theme: str) -> tuple:
    """
    Run 3 searches and score 1-10. Returns (score, evidence_str).
    Scoring:
      +3  if paid tools/software found (commercial market exists)
      +2  if freelance/manual work patterns found
      +2  if workarounds/alternatives found
      +3  based on community size signals (result counts)
    """
    evidence_parts = []
    score = 0

    # Search 1: existing paid tools
    q1 = f'"{theme}" tool OR software pricing'
    d1 = ddg_search(q1)
    r1 = count_results(d1)
    if r1 >= 2:
        score += 3
        evidence_parts.append(f"paid_tools:{r1}_signals")
    elif r1 == 1:
        score += 1
        evidence_parts.append(f"paid_tools:{r1}_signals")
    else:
        evidence_parts.append("paid_tools:none")
    time.sleep(1)  # be polite to DDG

    # Search 2: manual work / freelance patterns
    q2 = f'"{theme}" "looking for" "manually" OR "spreadsheet"'
    d2 = ddg_search(q2)
    r2 = count_results(d2)
    if r2 >= 2:
        score += 2
        evidence_parts.append(f"manual_patterns:{r2}_signals")
    elif r2 == 1:
        score += 1
        evidence_parts.append(f"manual_patterns:{r2}_signals")
    else:
        evidence_parts.append("manual_patterns:none")
    time.sleep(1)

    # Search 3: workarounds / alternatives
    q3 = f'"{theme}" workaround OR "alternative to"'
    d3 = ddg_search(q3)
    r3 = count_results(d3)
    if r3 >= 2:
        score += 2
        evidence_parts.append(f"workarounds:{r3}_signals")
    elif r3 == 1:
        score += 1
        evidence_parts.append(f"workarounds:{r3}_signals")
    else:
        evidence_parts.append("workarounds:none")

    # Community size bonus: sum of all signals
    total_signals = r1 + r2 + r3
    if total_signals >= 10:
        score += 3
    elif total_signals >= 5:
        score += 2
    elif total_signals >= 2:
        score += 1
    evidence_parts.append(f"total_signals:{total_signals}")

    # Cap at 10
    score = min(10, max(1, score))
    evidence = "; ".join(evidence_parts)
    return score, evidence


def update_cluster_validation(cluster_id: int, score: float, evidence: str) -> bool:
    """Call db_clusters.py update_validation."""
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(TOOLS_DIR / "db_clusters.py"),
                "update_validation",
                str(cluster_id),
                str(score),
                evidence,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("[validate_demand] db_clusters.py timed out", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_demand.py <niche>")
        sys.exit(1)

    niche = sys.argv[1]
    clusters = load_top_clusters(niche)

    if not clusters:
        result = {
            "niche": niche,
            "clusters_validated": 0,
            "message": "No clusters found with 3+ mentions",
        }
        print(json.dumps(result))
        return

    print(f"[validate_demand] Validating {len(clusters)} clusters for '{niche}'", file=sys.stderr)

    validated = 0
    results_detail = []

    for cluster in clusters:
        cluster_id = cluster["id"]
        theme = cluster["theme"]
        print(f"[validate_demand] Scoring cluster '{theme}'...", file=sys.stderr)

        score, evidence = score_cluster(theme)
        ok = update_cluster_validation(cluster_id, score, evidence)

        if ok:
            validated += 1
        results_detail.append({
            "cluster_id": cluster_id,
            "theme": theme,
            "validation_score": score,
            "evidence": evidence,
        })
        print(f"[validate_demand] '{theme}' -> score={score}, evidence={evidence}", file=sys.stderr)
        time.sleep(2)  # rate limit between clusters

    summary = {
        "niche": niche,
        "clusters_validated": validated,
        "results": results_detail,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
