"""
Extract structured pain points from raw scraped content.
Reads raw text files, calls LLM API (OpenRouter) to extract pain objects.
Usage: python extract_pain.py "e-commerce logistics" [optional: path/to/raw/file.txt]
Saves to data/pains.db via db_pains.py
"""

import sys
import json
import subprocess
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
OUTPUT_DIR = WORKSPACE_DIR / "output" / "raw"

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-4o-mini"

EXTRACTION_PROMPT = """\
Analyze this web content and extract all pain points, complaints, frustrations, and workarounds.
For each one found, output a JSON object with:
- raw_quote: exact quote (max 200 chars)
- source_url: the URL where it was found
- source_type: one of reddit/hackernews/github/producthunt/quora/indiehackers/forum
- pain_summary: one sentence description
- pain_type: one of time_waste/missing_tool/bad_ux/high_cost/manual_process
- intensity: 1-10 (1-3 minor, 4-6 frustrating, 7-8 nightmare, 9-10 losing money)
- social_proof: estimated upvotes/reactions count (0 if unknown)

Output a JSON array. If no pain points found, output [].
Content: {content}"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_env(env_path: Path) -> dict:
    """Parse KEY=VALUE lines from a .env file. Ignores comments and blanks."""
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


def call_llm(api_key: str, content: str) -> list:
    """Send content to OpenRouter and return extracted pain points as a list."""
    truncated = content[:12000]  # stay within context limits
    prompt = EXTRACTION_PROMPT.format(content=truncated)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/pain-hunter",
        "X-Title": "Pain Hunter Agent",
    }
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }

    try:
        resp = httpx.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"].strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        pains = json.loads(text)
        if isinstance(pains, list):
            return pains
        return []
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        print(f"[extract_pain] LLM request error: {exc}", file=sys.stderr)
        return []
    except json.JSONDecodeError as exc:
        print(f"[extract_pain] JSON parse error from LLM: {exc}", file=sys.stderr)
        return []


def save_pain_via_db(niche: str, pain: dict) -> bool:
    """Call db_pains.py save with the pain dict enriched with niche."""
    pain_with_niche = dict(pain)
    pain_with_niche["niche"] = niche

    required = ["raw_quote", "source_url", "source_type", "pain_summary",
                 "pain_type", "intensity"]
    for field in required:
        if field not in pain_with_niche or pain_with_niche[field] is None:
            if field == "source_url":
                pain_with_niche["source_url"] = ""
            elif field == "source_type":
                pain_with_niche["source_type"] = "forum"
            else:
                print(f"[extract_pain] Skipping pain missing field '{field}': {pain}", file=sys.stderr)
                return False

    # Clamp intensity
    try:
        pain_with_niche["intensity"] = max(1, min(10, int(pain_with_niche["intensity"])))
    except (ValueError, TypeError):
        pain_with_niche["intensity"] = 5

    pain_with_niche["social_proof"] = int(pain_with_niche.get("social_proof") or 0)

    # Truncate raw_quote to 200 chars
    if len(pain_with_niche.get("raw_quote", "")) > 200:
        pain_with_niche["raw_quote"] = pain_with_niche["raw_quote"][:197] + "..."

    payload_str = json.dumps(pain_with_niche, ensure_ascii=False)
    try:
        result = subprocess.run(
            [sys.executable, str(TOOLS_DIR / "db_pains.py"), "save", payload_str],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            print(f"[extract_pain] db_pains.py error: {result.stderr.strip()}", file=sys.stderr)
            return False
        return True
    except subprocess.TimeoutExpired:
        print("[extract_pain] db_pains.py timed out", file=sys.stderr)
        return False


def find_raw_files(niche: str) -> list:
    """Return all .txt files under output/raw/[niche]/[date]/ directories."""
    slug = niche.lower().replace(" ", "_").replace("-", "_")
    niche_dir = OUTPUT_DIR / slug
    if not niche_dir.exists():
        # Also try original niche string as dir name
        niche_dir = OUTPUT_DIR / niche
    if not niche_dir.exists():
        return []
    files = sorted(niche_dir.rglob("*.txt"))
    return files


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_pain.py <niche> [path/to/raw/file.txt]")
        sys.exit(1)

    niche = sys.argv[1]
    specific_file = sys.argv[2] if len(sys.argv) > 2 else None

    # Load API key
    env = load_env(ENV_FILE)
    api_key = env.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("[extract_pain] ERROR: OPENROUTER_API_KEY not found in profiles/pain_hunter/.env",
              file=sys.stderr)
        sys.exit(1)

    # Collect files to process
    if specific_file:
        files = [Path(specific_file)]
    else:
        files = find_raw_files(niche)

    if not files:
        print(json.dumps({"niche": niche, "pains_extracted": 0, "files_processed": 0,
                          "error": "No raw .txt files found"}))
        return

    total_pains = 0
    files_processed = 0
    files_failed = 0

    for file_path in files:
        if not file_path.exists():
            print(f"[extract_pain] File not found: {file_path}", file=sys.stderr)
            files_failed += 1
            continue

        content = file_path.read_text(encoding="utf-8", errors="replace")
        if not content.strip():
            continue

        print(f"[extract_pain] Processing {file_path.name} ({len(content)} chars)...",
              file=sys.stderr)
        pains = call_llm(api_key, content)
        files_processed += 1

        saved = 0
        for pain in pains:
            if save_pain_via_db(niche, pain):
                saved += 1

        total_pains += saved
        print(f"[extract_pain] {file_path.name}: {len(pains)} found, {saved} saved",
              file=sys.stderr)

    summary = {
        "niche": niche,
        "pains_extracted": total_pains,
        "files_processed": files_processed,
        "files_failed": files_failed,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
