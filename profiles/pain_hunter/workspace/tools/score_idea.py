"""
Score an idea on Desirability, Viability, Feasibility, Timing.
Usage: python score_idea.py [idea_id]
Updates data/ideas.db with scores
"""

import sys
import json
import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

TOOLS_DIR = Path(__file__).parent
PROFILE_DIR = TOOLS_DIR.parents[2]
DATA_DIR = PROFILE_DIR / "data"
IDEAS_DB = DATA_DIR / "ideas.db"
CLUSTERS_DB = DATA_DIR / "clusters.db"

# Feasibility proxies by solution type (higher = easier to build)
FEASIBILITY_BY_SOLUTION_TYPE = {
    "chrome extension": 8,
    "chrome_extension": 8,
    "api": 7,
    "saas": 6,
    "service": 5,
    "community": 7,
}
DEFAULT_FEASIBILITY = 6

# Max social proof value used for normalization (anything above is capped at 1.0)
MAX_SOCIAL_PROOF = 10000

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_idea(idea_id: int) -> dict:
    """Load an idea record from ideas.db."""
    if not IDEAS_DB.exists():
        return {}
    conn = sqlite3.connect(str(IDEAS_DB))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM ideas WHERE id = ?", (int(idea_id),)).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def load_latest_idea() -> dict:
    """Load the most recently created idea from ideas.db."""
    if not IDEAS_DB.exists():
        return {}
    conn = sqlite3.connect(str(IDEAS_DB))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM ideas ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def load_cluster(cluster_id: int) -> dict:
    """Load a cluster record from clusters.db."""
    if not CLUSTERS_DB.exists():
        return {}
    conn = sqlite3.connect(str(CLUSTERS_DB))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM clusters WHERE id = ?", (int(cluster_id),)
        ).fetchone()
        if not row:
            return {}
        d = dict(row)
        for field in ("pain_ids", "source_types"):
            if d.get(field) and isinstance(d[field], str):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d
    finally:
        conn.close()


def compute_source_diversity(source_types) -> float:
    """Normalize source diversity: unique source count / 7 known source types, capped at 1."""
    if not source_types:
        return 0.0
    if isinstance(source_types, str):
        try:
            source_types = json.loads(source_types)
        except (json.JSONDecodeError, TypeError):
            source_types = [source_types]
    known_sources = {
        "reddit", "hackernews", "github", "producthunt", "quora", "indiehackers", "forum"
    }
    unique = {s.lower() for s in source_types if s} & known_sources
    return min(1.0, len(unique) / 3.0)  # normalize over 3 = good diversity


def compute_desirability(avg_intensity: float, total_social_proof: int,
                          source_diversity: float) -> float:
    """
    Desirability = avg_intensity/10 * 0.5
               + min(social_proof/MAX_SOCIAL_PROOF, 1) * 0.3
               + source_diversity * 0.2
    Result scaled to 0-10.
    """
    intensity_norm = max(0.0, min(1.0, avg_intensity / 10.0))
    social_norm = min(1.0, (total_social_proof or 0) / MAX_SOCIAL_PROOF)
    score = (intensity_norm * 0.5 + social_norm * 0.3 + source_diversity * 0.2) * 10
    return round(score, 2)


def compute_feasibility(solution_type: str) -> float:
    """Look up feasibility from the solution_type proxy table."""
    if not solution_type:
        return float(DEFAULT_FEASIBILITY)
    key = solution_type.lower().replace(" ", "_")
    # Also try without underscore
    value = FEASIBILITY_BY_SOLUTION_TYPE.get(key)
    if value is None:
        value = FEASIBILITY_BY_SOLUTION_TYPE.get(solution_type.lower(), DEFAULT_FEASIBILITY)
    return float(value)


def update_scores_via_db(idea_id: int, desirability: float, viability: float,
                          feasibility: float, timing: float) -> dict:
    """Call db_ideas.py update_scores."""
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(TOOLS_DIR / "db_ideas.py"),
                "update_scores",
                str(idea_id),
                str(desirability),
                str(viability),
                str(feasibility),
                str(timing),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            print(f"[score_idea] db_ideas.py error: {result.stderr.strip()}", file=sys.stderr)
            return {}
        return json.loads(result.stdout.strip())
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f"[score_idea] db_ideas.py call failed: {exc}", file=sys.stderr)
        return {}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    if len(sys.argv) < 2:
        # Try to score the latest idea
        idea = load_latest_idea()
        if not idea:
            print("Usage: python score_idea.py <idea_id>")
            print("[score_idea] No ideas found in database", file=sys.stderr)
            sys.exit(1)
        print(f"[score_idea] No idea_id given, using latest idea id={idea['id']}", file=sys.stderr)
    else:
        idea_id = int(sys.argv[1])
        idea = load_idea(idea_id)

    if not idea:
        result = {"error": f"Idea not found"}
        print(json.dumps(result))
        sys.exit(1)

    idea_id = idea["id"]
    cluster_id = idea.get("cluster_id")
    solution_type = idea.get("solution_type", "SaaS")

    # Load cluster for stats
    cluster = {}
    if cluster_id:
        cluster = load_cluster(int(cluster_id))

    avg_intensity = cluster.get("avg_intensity", 5.0) or 5.0
    total_social_proof = cluster.get("total_social_proof", 0) or 0
    validation_score = cluster.get("validation_score", 5.0) or 5.0
    source_types = cluster.get("source_types", [])

    source_diversity = compute_source_diversity(source_types)

    # Compute scores
    desirability = compute_desirability(avg_intensity, total_social_proof, source_diversity)
    viability = float(validation_score)
    feasibility = compute_feasibility(solution_type)
    timing = 7.0  # default unless niche has specific signals

    # Composite: D*0.35 + V*0.35 + F*0.2 + T*0.1
    composite = round(
        desirability * 0.35 + viability * 0.35 + feasibility * 0.2 + timing * 0.1, 2
    )

    print(f"[score_idea] idea_id={idea_id} | D={desirability} V={viability} "
          f"F={feasibility} T={timing} -> composite={composite}", file=sys.stderr)

    updated = update_scores_via_db(idea_id, desirability, viability, feasibility, timing)

    summary = {
        "idea_id": idea_id,
        "title": idea.get("title", ""),
        "desirability": desirability,
        "viability": viability,
        "feasibility": feasibility,
        "timing": timing,
        "composite": composite,
        "score_composite": updated.get("score_composite", composite),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
