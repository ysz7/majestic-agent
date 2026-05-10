"""
Generate daily digest: top clusters, new ideas, opportunity alerts.
Saves to output/digest/[date].md
"""

import sys
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

TOOLS_DIR = Path(__file__).parent
WORKSPACE_DIR = TOOLS_DIR.parent
PROFILE_DIR = WORKSPACE_DIR.parent
DATA_DIR = PROFILE_DIR / "data"
DIGEST_DIR = WORKSPACE_DIR / "output" / "digest"

CLUSTERS_DB = DATA_DIR / "clusters.db"
IDEAS_DB = DATA_DIR / "ideas.db"
PAINS_DB = DATA_DIR / "pains.db"
NICHES_DB = DATA_DIR / "niches.db"

ALERT_THRESHOLD = 8.0

# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_high_value_clusters(threshold: float = ALERT_THRESHOLD) -> list:
    """Clusters with validation >= threshold that have no idea generated yet."""
    if not CLUSTERS_DB.exists():
        return []
    conn = sqlite3.connect(str(CLUSTERS_DB))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT c.id, c.niche, c.theme, c.validation_score,
                   c.mention_count, c.avg_intensity, c.total_social_proof
            FROM clusters c
            WHERE c.validation_score >= ? AND c.active = 1
            ORDER BY c.validation_score DESC, c.avg_intensity DESC
            """,
            (threshold,),
        ).fetchall()
        clusters = [dict(row) for row in rows]
    finally:
        conn.close()

    # Filter out clusters that already have an idea
    if not IDEAS_DB.exists():
        return clusters

    conn2 = sqlite3.connect(str(IDEAS_DB))
    try:
        idea_cluster_ids = {
            row[0]
            for row in conn2.execute("SELECT cluster_id FROM ideas").fetchall()
        }
    finally:
        conn2.close()

    return [c for c in clusters if c["id"] not in idea_cluster_ids]


def load_top_ideas(limit: int = 10) -> list:
    """Top ideas this week sorted by composite score."""
    if not IDEAS_DB.exists():
        return []
    conn = sqlite3.connect(str(IDEAS_DB))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, niche, title, solution_type,
                   score_composite, score_desirability, score_viability,
                   score_feasibility, score_timing, output_path, created_at
            FROM ideas
            ORDER BY score_composite DESC, created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def load_top_clusters_per_niche(top_n: int = 5) -> dict:
    """Top clusters per niche, keyed by niche name."""
    if not CLUSTERS_DB.exists():
        return {}
    conn = sqlite3.connect(str(CLUSTERS_DB))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT niche, id, theme, mention_count, avg_intensity,
                   total_social_proof, validation_score
            FROM clusters
            WHERE active = 1
            ORDER BY niche, validation_score DESC, mention_count DESC
            """,
        ).fetchall()
        clusters = [dict(row) for row in rows]
    finally:
        conn.close()

    by_niche: dict = {}
    for c in clusters:
        n = c["niche"]
        if n not in by_niche:
            by_niche[n] = []
        if len(by_niche[n]) < top_n:
            by_niche[n].append(c)
    return by_niche


def load_scan_coverage() -> dict:
    """Return pain counts per niche scraped today."""
    if not PAINS_DB.exists():
        return {}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = sqlite3.connect(str(PAINS_DB))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT niche, COUNT(*) as cnt
            FROM pains
            WHERE date_found LIKE ?
            GROUP BY niche
            ORDER BY cnt DESC
            """,
            (f"{today}%",),
        ).fetchall()
        return {row["niche"]: row["cnt"] for row in rows}
    finally:
        conn.close()


def load_active_niches() -> list:
    """Return all non-archived niches."""
    if not NICHES_DB.exists():
        return []
    conn = sqlite3.connect(str(NICHES_DB))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT name, status, pain_count FROM niches WHERE status != 'archived' "
            "ORDER BY priority DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Markdown builders
# ---------------------------------------------------------------------------


def fmt_score(value) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "—"


def build_digest(date_str: str) -> str:
    alert_clusters = load_high_value_clusters()
    top_ideas = load_top_ideas()
    clusters_by_niche = load_top_clusters_per_niche()
    scan_coverage = load_scan_coverage()
    active_niches = load_active_niches()

    lines = [f"# Pain Hunter Digest — {date_str}", ""]

    # ---- Opportunity Alerts ----
    lines.append("## Opportunity Alerts")
    lines.append("")
    if alert_clusters:
        for c in alert_clusters:
            lines.append(
                f"- **[{c['niche']}]** `{c['theme']}` — "
                f"validation {fmt_score(c['validation_score'])}/10, "
                f"{c['mention_count']} mentions, "
                f"avg intensity {fmt_score(c['avg_intensity'])}/10"
            )
    else:
        lines.append("_No new high-value clusters without ideas yet._")
    lines.append("")

    # ---- Top Ideas ----
    lines.append("## Top Ideas This Week")
    lines.append("")
    if top_ideas:
        lines.append("| # | Niche | Title | Type | D | V | F | T | Score |")
        lines.append("|---|-------|-------|------|---|---|---|---|-------|")
        for i, idea in enumerate(top_ideas, 1):
            path = idea.get("output_path", "")
            title_link = f"[{idea['title']}]({path})" if path else idea.get("title", "—")
            lines.append(
                f"| {i} | {idea['niche']} | {title_link} | {idea.get('solution_type','—')} "
                f"| {fmt_score(idea.get('score_desirability'))} "
                f"| {fmt_score(idea.get('score_viability'))} "
                f"| {fmt_score(idea.get('score_feasibility'))} "
                f"| {fmt_score(idea.get('score_timing'))} "
                f"| **{fmt_score(idea.get('score_composite'))}** |"
            )
    else:
        lines.append("_No ideas generated yet._")
    lines.append("")

    # ---- Active Clusters ----
    lines.append("## Active Clusters")
    lines.append("")
    if clusters_by_niche:
        for niche, clusters in clusters_by_niche.items():
            lines.append(f"### {niche}")
            lines.append("")
            lines.append("| Theme | Mentions | Avg Intensity | Social Proof | Validation |")
            lines.append("|-------|----------|---------------|--------------|------------|")
            for c in clusters:
                lines.append(
                    f"| {c['theme']} "
                    f"| {c['mention_count']} "
                    f"| {fmt_score(c['avg_intensity'])} "
                    f"| {c.get('total_social_proof', 0)} "
                    f"| {fmt_score(c['validation_score'])} |"
                )
            lines.append("")
    else:
        lines.append("_No clusters found._")
        lines.append("")

    # ---- Scan Coverage ----
    lines.append("## Scan Coverage")
    lines.append("")
    if active_niches:
        lines.append("| Niche | Status | Total Pains | Scanned Today |")
        lines.append("|-------|--------|-------------|---------------|")
        for n in active_niches:
            today_count = scan_coverage.get(n["name"], 0)
            lines.append(
                f"| {n['name']} | {n['status']} | {n.get('pain_count', 0)} | {today_count} |"
            )
    else:
        lines.append("_No active niches tracked._")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    digest_content = build_digest(date_str)

    # Save to output/digest/[date].md
    DIGEST_DIR.mkdir(parents=True, exist_ok=True)
    digest_path = DIGEST_DIR / f"{date_str}.md"
    digest_path.write_text(digest_content, encoding="utf-8")

    # Count key stats for summary
    alert_count = len(load_high_value_clusters())
    idea_count = len(load_top_ideas(100))

    summary = {
        "date": date_str,
        "digest_path": str(digest_path),
        "opportunity_alerts": alert_count,
        "total_ideas": idea_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(summary))

    print(f"[digest] Digest saved to {digest_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
