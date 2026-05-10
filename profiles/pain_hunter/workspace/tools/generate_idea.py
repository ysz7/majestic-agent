"""
Generate structured business idea report from a validated cluster.
Usage: python generate_idea.py "e-commerce logistics" [cluster_id]
Saves to output/ideas/[niche]/[idea-name].md and data/ideas.db
"""

import sys
import json
import sqlite3
import subprocess
import re
from pathlib import Path
from datetime import datetime
import httpx

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

TOOLS_DIR = Path(__file__).parent
WORKSPACE_DIR = TOOLS_DIR.parent
PROFILE_DIR = WORKSPACE_DIR.parent
ENV_FILE = PROFILE_DIR / ".env"
DATA_DIR = PROFILE_DIR / "data"
CLUSTERS_DB = DATA_DIR / "clusters.db"
PAINS_DB = DATA_DIR / "pains.db"
IDEAS_OUTPUT_DIR = WORKSPACE_DIR / "output" / "ideas"

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-4o-mini"

IDEA_PROMPT = """\
Based on these validated pain points, generate a business idea report.

Niche: {niche}
Pain cluster: {theme}
Pain points (with quotes and sources):
{pains_section}
Validation score: {validation_score}/10
Evidence: {validation_evidence}

Write a structured business idea report with these sections:

## PROBLEM
Who has it, how often, what it costs them.

## IDEA
What it does. Customer outcome, not technology.

## TARGET CUSTOMER
Specific segment with context.

## SOLUTION TYPE
One of: SaaS / Chrome Extension / API / Service / Community

## HOW IT WORKS
3-5 bullets from customer perspective.

## MONETIZATION
Model, price range, who pays.

## EXISTING ALTERNATIVES
What people use today and why it's insufficient.

## UNFAIR ADVANTAGE OPPORTUNITIES
What makes this defensible or hard to copy.

## RISKS
Top 3 risks.

## SOURCES
List all source URLs used.

Important: cite sources for every claim. Be specific and direct."""

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


def load_cluster(niche: str, cluster_id: int = None) -> dict:
    """Load the top validated cluster (or a specific one) from clusters.db."""
    if not CLUSTERS_DB.exists():
        return {}
    conn = sqlite3.connect(str(CLUSTERS_DB))
    conn.row_factory = sqlite3.Row
    try:
        if cluster_id:
            row = conn.execute(
                "SELECT * FROM clusters WHERE id = ?", (cluster_id,)
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT * FROM clusters
                WHERE niche = ? AND mention_count >= 3 AND active = 1
                ORDER BY validation_score DESC, avg_intensity DESC
                LIMIT 1
                """,
                (niche,),
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


def load_pains_for_cluster(pain_ids: list) -> list:
    """Load pain records from pains.db for the given IDs."""
    if not PAINS_DB.exists() or not pain_ids:
        return []
    conn = sqlite3.connect(str(PAINS_DB))
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ",".join("?" * len(pain_ids))
        rows = conn.execute(
            f"SELECT id, pain_summary, raw_quote, source_url, source_type, intensity, social_proof "
            f"FROM pains WHERE id IN ({placeholders})",
            [int(pid) for pid in pain_ids],
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def build_pains_section(pains: list) -> str:
    lines = []
    for p in pains:
        quote = p.get("raw_quote", "").replace("\n", " ").strip()
        url = p.get("source_url", "")
        summary = p.get("pain_summary", "")
        intensity = p.get("intensity", "?")
        lines.append(f'- [{p["source_type"]}] "{quote}" (intensity: {intensity}/10)')
        lines.append(f'  Summary: {summary}')
        if url:
            lines.append(f'  Source: {url}')
    return "\n".join(lines)


def call_llm(api_key: str, prompt: str) -> str:
    """Call OpenRouter LLM and return the raw text response."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/pain-hunter",
        "X-Title": "Pain Hunter Agent",
    }
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.5,
        "max_tokens": 2000,
    }
    try:
        resp = httpx.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        print(f"[generate_idea] LLM error: {exc}", file=sys.stderr)
        return ""


def slugify(text: str) -> str:
    """Convert a string to a URL-friendly slug."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")[:60]


def extract_title_from_report(report_text: str, theme: str) -> str:
    """Try to extract a product name or short title from the report."""
    # Look for ## IDEA section
    match = re.search(r"## IDEA\s*\n(.+?)(?=\n##|\Z)", report_text, re.DOTALL | re.IGNORECASE)
    if match:
        first_line = match.group(1).strip().splitlines()[0].strip()
        if first_line and len(first_line) < 80:
            return first_line
    return theme[:60]


def extract_solution_type(report_text: str) -> str:
    """Extract solution type from the report."""
    match = re.search(
        r"## SOLUTION TYPE\s*\n(.+?)(?=\n##|\Z)", report_text, re.DOTALL | re.IGNORECASE
    )
    if match:
        text = match.group(1).strip().splitlines()[0].strip()
        for st in ("SaaS", "Chrome Extension", "API", "Service", "Community"):
            if st.lower() in text.lower():
                return st
    return "SaaS"


def extract_sources(report_text: str) -> list:
    """Extract URLs from the SOURCES section."""
    match = re.search(r"## SOURCES\s*\n(.+?)(?=\n##|\Z)", report_text, re.DOTALL | re.IGNORECASE)
    if not match:
        return []
    section = match.group(1)
    urls = re.findall(r"https?://\S+", section)
    return list(set(urls))


def save_idea_via_db(
    niche: str, cluster_id: int, title: str, slug: str, solution_type: str,
    report_text: str, report_path: str, sources: list,
) -> dict:
    """Call db_ideas.py save with the extracted fields."""
    # Extract sections from report
    def extract_section(name: str) -> str:
        match = re.search(
            rf"## {re.escape(name)}\s*\n(.+?)(?=\n##|\Z)", report_text, re.DOTALL | re.IGNORECASE
        )
        return match.group(1).strip() if match else ""

    payload = {
        "niche": niche,
        "cluster_id": cluster_id,
        "title": title,
        "problem": extract_section("PROBLEM"),
        "idea": extract_section("IDEA"),
        "target_customer": extract_section("TARGET CUSTOMER"),
        "solution_type": solution_type,
        "monetization": extract_section("MONETIZATION"),
        "alternatives": extract_section("EXISTING ALTERNATIVES"),
        "risks": extract_section("RISKS"),
        "sources": sources,
        "output_path": str(report_path),
    }
    payload_str = json.dumps(payload, ensure_ascii=False)
    try:
        result = subprocess.run(
            [sys.executable, str(TOOLS_DIR / "db_ideas.py"), "save", payload_str],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            print(f"[generate_idea] db_ideas.py error: {result.stderr.strip()}", file=sys.stderr)
            return {}
        return json.loads(result.stdout.strip())
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f"[generate_idea] db_ideas.py call failed: {exc}", file=sys.stderr)
        return {}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_idea.py <niche> [cluster_id]")
        sys.exit(1)

    niche = sys.argv[1]
    cluster_id = int(sys.argv[2]) if len(sys.argv) > 2 else None

    env = load_env(ENV_FILE)
    api_key = env.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("[generate_idea] ERROR: OPENROUTER_API_KEY not found in .env", file=sys.stderr)
        sys.exit(1)

    cluster = load_cluster(niche, cluster_id)
    if not cluster:
        result = {"niche": niche, "error": "No suitable cluster found"}
        print(json.dumps(result))
        return

    pain_ids = cluster.get("pain_ids", [])
    pains = load_pains_for_cluster(pain_ids)

    if not pains:
        result = {"niche": niche, "error": f"No pains found for cluster {cluster.get('id')}"}
        print(json.dumps(result))
        return

    print(f"[generate_idea] Generating idea for cluster '{cluster['theme']}' "
          f"({len(pains)} pains, validation={cluster.get('validation_score', 0)}/10)",
          file=sys.stderr)

    pains_section = build_pains_section(pains)
    prompt = IDEA_PROMPT.format(
        niche=niche,
        theme=cluster["theme"],
        pains_section=pains_section,
        validation_score=cluster.get("validation_score", 0),
        validation_evidence=cluster.get("validation_evidence", "N/A"),
    )

    report_text = call_llm(api_key, prompt)
    if not report_text:
        result = {"niche": niche, "error": "LLM returned empty response"}
        print(json.dumps(result))
        return

    # Build title and slug
    title = extract_title_from_report(report_text, cluster["theme"])
    slug = slugify(title)
    solution_type = extract_solution_type(report_text)
    sources = extract_sources(report_text)

    # Enrich report with metadata header
    niche_slug = slugify(niche)
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    full_report = (
        f"# {title}\n\n"
        f"**Niche:** {niche}  \n"
        f"**Cluster:** {cluster['theme']}  \n"
        f"**Validation Score:** {cluster.get('validation_score', 0)}/10  \n"
        f"**Generated:** {date_str}  \n\n"
        f"---\n\n"
        f"{report_text}\n"
    )

    # Save markdown file
    ideas_dir = IDEAS_OUTPUT_DIR / niche_slug
    ideas_dir.mkdir(parents=True, exist_ok=True)
    report_path = ideas_dir / f"{slug}.md"
    report_path.write_text(full_report, encoding="utf-8")
    print(f"[generate_idea] Report saved to {report_path}", file=sys.stderr)

    # Save to DB
    saved = save_idea_via_db(
        niche=niche,
        cluster_id=cluster["id"],
        title=title,
        slug=slug,
        solution_type=solution_type,
        report_text=report_text,
        report_path=str(report_path),
        sources=sources,
    )

    summary = {
        "niche": niche,
        "cluster_id": cluster["id"],
        "idea_id": saved.get("id"),
        "title": title,
        "slug": slug,
        "solution_type": solution_type,
        "report_path": str(report_path),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
