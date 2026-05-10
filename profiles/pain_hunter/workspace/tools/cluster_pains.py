"""
Group pain points into clusters by theme. Min 3 mentions per cluster.
Usage: python cluster_pains.py "e-commerce logistics"
Reads from data/pains.db, saves to data/clusters.db
"""

import sys
import json
import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime
import httpx

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

TOOLS_DIR = Path(__file__).parent
PROFILE_DIR = TOOLS_DIR.parents[2]
ENV_FILE = PROFILE_DIR / ".env"
DATA_DIR = PROFILE_DIR / "data"
PAINS_DB = DATA_DIR / "pains.db"

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-4o-mini"
MIN_CLUSTER_SIZE = 3

CLUSTER_PROMPT = """\
Group these pain points into semantic clusters. Each cluster must have at least 3 items.
Pain points (format: ID: summary):
{pains}

Return JSON array of clusters:
[{{"theme": "clear theme name", "pain_ids": [1,2,3], "reasoning": "why grouped"}}]
Only include clusters with 3+ members. Discard singletons."""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_env(env_path: Path) -> dict:
    env = {}
    if not env_path.exists():
        return env
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def load_unclustered_pains(niche: str) -> list:
    """Load unclustered pains directly from pains.db."""
    if not PAINS_DB.exists():
        return []
    conn = sqlite3.connect(str(PAINS_DB))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, pain_summary, intensity, social_proof, source_type, source_url
            FROM pains
            WHERE niche = ? AND clustered = 0
            ORDER BY intensity DESC, social_proof DESC
            """,
            (niche,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def call_llm_cluster(api_key: str, pains: list) -> list:
    """Send pain summaries to OpenRouter and return cluster groups."""
    pains_text = "\n".join(f"{p['id']}: {p['pain_summary']}" for p in pains)
    prompt = CLUSTER_PROMPT.format(pains=pains_text)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/pain-hunter",
        "X-Title": "Pain Hunter Agent",
    }
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }

    try:
        resp = httpx.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=90)
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"].strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        clusters = json.loads(text)
        if isinstance(clusters, list):
            return clusters
        return []
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        print(f"[cluster_pains] LLM request error: {exc}", file=sys.stderr)
        return []
    except json.JSONDecodeError as exc:
        print(f"[cluster_pains] JSON parse error: {exc}", file=sys.stderr)
        return []


def save_cluster_via_db(niche: str, theme: str, pain_ids: list, avg_intensity: float,
                         total_social_proof: int, source_types: list) -> dict:
    """Call db_clusters.py save."""
    payload = {
        "niche": niche,
        "theme": theme,
        "pain_ids": pain_ids,
        "avg_intensity": round(avg_intensity, 2),
        "total_social_proof": total_social_proof,
        "source_types": source_types,
    }
    payload_str = json.dumps(payload)
    try:
        result = subprocess.run(
            [sys.executable, str(TOOLS_DIR / "db_clusters.py"), "save", payload_str],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            print(f"[cluster_pains] db_clusters.py error: {result.stderr.strip()}", file=sys.stderr)
            return {}
        return json.loads(result.stdout.strip())
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f"[cluster_pains] db_clusters.py call failed: {exc}", file=sys.stderr)
        return {}


def mark_pains_clustered(pain_ids: list) -> None:
    """Call db_pains.py mark_clustered for the given IDs."""
    if not pain_ids:
        return
    str_ids = [str(i) for i in pain_ids]
    try:
        subprocess.run(
            [sys.executable, str(TOOLS_DIR / "db_pains.py"), "mark_clustered"] + str_ids,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        print("[cluster_pains] db_pains.py mark_clustered timed out", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    if len(sys.argv) < 2:
        print("Usage: python cluster_pains.py <niche>")
        sys.exit(1)

    niche = sys.argv[1]

    env = load_env(ENV_FILE)
    api_key = env.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("[cluster_pains] ERROR: OPENROUTER_API_KEY not found in profiles/pain_hunter/.env",
              file=sys.stderr)
        sys.exit(1)

    pains = load_unclustered_pains(niche)
    if len(pains) < MIN_CLUSTER_SIZE:
        result = {
            "niche": niche,
            "clusters_created": 0,
            "largest_cluster": 0,
            "message": f"Not enough unclustered pains ({len(pains)}), need >= {MIN_CLUSTER_SIZE}",
        }
        print(json.dumps(result))
        return

    print(f"[cluster_pains] Loaded {len(pains)} unclustered pains for '{niche}'", file=sys.stderr)

    # Build lookup by id
    pain_by_id = {p["id"]: p for p in pains}

    # Get LLM clusters
    llm_clusters = call_llm_cluster(api_key, pains)

    clusters_created = 0
    largest_cluster = 0
    all_clustered_ids = []

    for cluster in llm_clusters:
        theme = cluster.get("theme", "").strip()
        pain_ids = [int(pid) for pid in cluster.get("pain_ids", [])
                    if int(pid) in pain_by_id]

        if len(pain_ids) < MIN_CLUSTER_SIZE:
            continue

        # Calculate stats from actual pain data
        member_pains = [pain_by_id[pid] for pid in pain_ids if pid in pain_by_id]
        if not member_pains:
            continue

        avg_intensity = sum(p["intensity"] for p in member_pains) / len(member_pains)
        total_social_proof = sum(p.get("social_proof", 0) or 0 for p in member_pains)
        source_types = list({p["source_type"] for p in member_pains if p.get("source_type")})

        saved = save_cluster_via_db(
            niche=niche,
            theme=theme,
            pain_ids=pain_ids,
            avg_intensity=avg_intensity,
            total_social_proof=total_social_proof,
            source_types=source_types,
        )

        if saved.get("saved"):
            clusters_created += 1
            all_clustered_ids.extend(pain_ids)
            if len(pain_ids) > largest_cluster:
                largest_cluster = len(pain_ids)
            print(f"[cluster_pains] Cluster '{theme}': {len(pain_ids)} pains", file=sys.stderr)

    # Mark pains as clustered
    mark_pains_clustered(list(set(all_clustered_ids)))

    summary = {
        "niche": niche,
        "clusters_created": clusters_created,
        "largest_cluster": largest_cluster,
        "pains_clustered": len(set(all_clustered_ids)),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
