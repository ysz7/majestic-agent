"""
collect_news.py — Collect news articles by category using DuckDuckGo.

Usage:
    python collect_news.py tech [--limit 5]
    python collect_news.py funding [--limit 5]
    python collect_news.py macro [--limit 5]
    python collect_news.py policy [--limit 5]
    python collect_news.py geopolitics [--limit 5]
    python collect_news.py custom --query "AI regulation EU 2026" [--category tech] [--limit 5]
"""

import sys
import json
import asyncio
import subprocess
import argparse
import re
import httpx
from pathlib import Path
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_TOOLS_DIR = Path(__file__).parent
_PROFILE_ROOT = Path(__file__).parents[2]   # = profiles/world_intel/
_PROJECT_ROOT = Path(__file__).parents[4]   # = c:/ysz/DEV/majestic-agent/
_DATA_DIR = _PROFILE_ROOT / "data"
_OUTPUT_DIR = _PROFILE_ROOT / "workspace" / "output"

# ---------------------------------------------------------------------------
# Category query templates
# ---------------------------------------------------------------------------

CATEGORY_QUERIES = {
    "tech": [
        'site:techcrunch.com OR site:theverge.com AI OR startup OR launch 2026',
        'site:venturebeat.com AI OR machine learning OR startup 2026',
        'site:arstechnica.com technology AI OR software 2026',
    ],
    "funding": [
        'site:techcrunch.com "raises" OR "raised" OR "series" million 2026',
        'site:venturebeat.com "funding" OR "investment" OR "raised" 2026',
        'site:news.crunchbase.com funding OR raised OR series 2026',
        '"seed round" OR "series A" OR "series B" OR "series C" startup 2026',
    ],
    "macro": [
        'site:reuters.com economy OR markets OR "interest rates" OR unemployment 2026',
        'site:cnbc.com markets OR economy OR GDP OR inflation 2026',
        'site:finance.yahoo.com markets OR stocks OR commodities 2026',
    ],
    "policy": [
        'site:politico.com technology OR AI OR regulation OR "data privacy" 2026',
        '"AI regulation" OR "AI Act" OR "data privacy" OR antitrust 2026',
        'site:reuters.com regulation OR "central bank" OR policy 2026',
    ],
    "geopolitics": [
        'site:reuters.com geopolitics OR sanctions OR trade OR alliance 2026',
        '"trade war" OR "sanctions" OR "sovereign wealth" OR "strategic partnership" 2026',
        'site:politico.com geopolitics OR "foreign policy" OR defense 2026',
    ],
}

# ---------------------------------------------------------------------------
# Env / LLM helpers
# ---------------------------------------------------------------------------


def _load_env() -> dict:
    env = {}
    for path in [_PROJECT_ROOT / ".env", _PROFILE_ROOT / ".env"]:
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()  # later file overrides earlier
    return env


def _call_llm(prompt: str, system: str, env: dict, max_tokens: int = 1500) -> str:
    api_key = env.get("OPENROUTER_API_KEY") or env.get("ANTHROPIC_API_KEY") or env.get("OPENAI_API_KEY")
    ollama_url = env.get("OLLAMA_BASE_URL")
    if not api_key and not ollama_url:
        return ""
    if ollama_url and not api_key:
        url = f"{ollama_url.rstrip('/')}/v1/chat/completions"
        model = env.get("OLLAMA_MODEL", "llama3.2")
        headers = {"Content-Type": "application/json"}
    else:
        url = "https://openrouter.ai/api/v1/chat/completions"
        model = env.get("MAJESTIC_MODEL_REASON", "anthropic/claude-sonnet-4-5")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/majestic-agent",
            "X-Title": "Majestic World Intel Agent",
        }
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    try:
        resp = httpx.post(url, headers=headers, json=body, timeout=120)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        return f"[LLM error: {exc}]"


# ---------------------------------------------------------------------------
# DuckDuckGo search / fetch
# ---------------------------------------------------------------------------


async def _ddg_search(query: str, max_results: int = 5) -> list[dict]:
    """DuckDuckGo HTML search. Returns list of {url, title, snippet}."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
    }
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        try:
            resp = await client.post("https://html.duckduckgo.com/html/", data={"q": query}, headers=headers)
            href_pat = re.compile(r'class="result__a"[^>]*href="([^"]+)"')
            title_pat = re.compile(r'class="result__a"[^>]*>([^<]+)<')
            snippet_pat = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL)
            hrefs = href_pat.findall(resp.text)
            titles = title_pat.findall(resp.text)
            snippets_raw = snippet_pat.findall(resp.text)
            results = []
            for i, href in enumerate(hrefs[:max_results]):
                m = re.search(r'uddg=([^&"]+)', href)
                url = m.group(1) if m else href
                for enc, dec in [("%3A", ":"), ("%2F", "/"), ("%3F", "?"), ("%3D", "="), ("%26", "&"), ("%25", "%")]:
                    url = url.replace(enc, dec)
                title = titles[i] if i < len(titles) else ""
                snippet = re.sub(r'<[^>]+>', ' ', snippets_raw[i]).strip() if i < len(snippets_raw) else ""
                results.append({"url": url, "title": title.strip(), "snippet": snippet})
            return results
        except Exception:
            return []


async def _fetch_article(url: str, max_chars: int = 4000) -> str:
    """Fetch URL and return plain text (stripped HTML)."""
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            text = re.sub(r'<script[^>]*>.*?</script>', ' ', resp.text, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:max_chars]
        except Exception:
            return ""


# ---------------------------------------------------------------------------
# DB subprocess helpers
# ---------------------------------------------------------------------------


def _url_exists(url: str) -> bool:
    """Check if URL is already in the news DB via db_news.py."""
    result = subprocess.run(
        [sys.executable, str(_TOOLS_DIR / "db_news.py"), "exists_url", url],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode == 0 and result.stdout.strip():
        try:
            data = json.loads(result.stdout.strip())
            return data.get("exists", False)
        except json.JSONDecodeError:
            return False
    return False


def _save_news(payload: dict) -> dict:
    """Save a news article to the DB via db_news.py."""
    payload_str = json.dumps(payload, ensure_ascii=False)
    try:
        result = subprocess.run(
            [sys.executable, str(_TOOLS_DIR / "db_news.py"), "save", payload_str],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout.strip())
        print(f"[collect_news] db_news.py save error: {result.stderr.strip()}", file=sys.stderr)
        return {}
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f"[collect_news] db_news.py save exception: {exc}", file=sys.stderr)
        return {}


# ---------------------------------------------------------------------------
# LLM helpers for summarisation and scoring
# ---------------------------------------------------------------------------


def _summarise_article(content: str, source: str, env: dict) -> str:
    system = "You are a concise news summarizer. Return only the summary, no preamble."
    prompt = (
        f"Given this article content from {source}, write a 2-3 sentence factual summary. "
        "Include: who did what, key numbers if any, date if mentioned. No editorial. No analysis.\n\n"
        f"Content:\n{content[:3000]}"
    )
    return _call_llm(prompt, system, env, max_tokens=300)


def _score_importance(summary: str, env: dict) -> int:
    system = "You are a financial analyst. Respond with valid JSON only."
    prompt = (
        "Score 1-5 importance of this news for investors/analysts tracking capital flows. "
        "5=landmark, 4=high, 3=medium, 2=low, 1=noise. "
        'Return JSON: {"importance": N}\n\n'
        f"News: {summary}"
    )
    raw = _call_llm(prompt, system, env, max_tokens=50)
    try:
        data = json.loads(raw)
        return int(data.get("importance", 3))
    except Exception:
        # Try to extract a digit from the response
        m = re.search(r'\d', raw)
        return int(m.group()) if m else 3


# ---------------------------------------------------------------------------
# Source domain extraction
# ---------------------------------------------------------------------------


def _extract_domain(url: str) -> str:
    """Return the bare domain name from a URL (e.g. 'techcrunch.com')."""
    m = re.search(r'https?://(?:www\.)?([^/]+)', url)
    return m.group(1) if m else url


def _url_to_slug(url: str) -> str:
    """Convert a URL into a safe filename slug."""
    slug = re.sub(r'https?://[^/]+/', '', url)
    slug = re.sub(r'[^a-zA-Z0-9_-]', '_', slug)
    return slug[:80]


# ---------------------------------------------------------------------------
# Core async collection logic
# ---------------------------------------------------------------------------


async def _collect(queries: list[str], category: str, limit: int, env: dict) -> dict:
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    raw_dir = _OUTPUT_DIR / "raw" / date_str / category
    raw_dir.mkdir(parents=True, exist_ok=True)

    seen_urls: set[str] = set()
    collected = 0
    skipped_dupes = 0
    articles = []

    for query in queries:
        results = await _ddg_search(query, max_results=limit)
        for result in results:
            url = result.get("url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            # Dedup check against DB
            if _url_exists(url):
                skipped_dupes += 1
                print(f"[collect_news] skipping duplicate: {url}", file=sys.stderr)
                continue

            # Fetch article content
            content = await _fetch_article(url)
            if not content:
                print(f"[collect_news] empty content, skipping: {url}", file=sys.stderr)
                continue

            source = _extract_domain(url)
            headline = result.get("title") or result.get("snippet", "")[:120]

            # Summarise
            summary = _summarise_article(content, source, env)
            if summary.startswith("[LLM error"):
                summary = result.get("snippet", "")[:500]

            # Score importance
            importance = _score_importance(summary, env)

            # Save raw content to disk
            slug = _url_to_slug(url)
            raw_file = raw_dir / f"{slug}.txt"
            try:
                raw_file.write_text(
                    f"URL: {url}\nSOURCE: {source}\nHEADLINE: {headline}\n\n{content}",
                    encoding="utf-8",
                )
            except Exception as exc:
                print(f"[collect_news] could not write raw file: {exc}", file=sys.stderr)

            # Save to DB
            payload = {
                "url": url,
                "headline": headline,
                "summary": summary,
                "source": source,
                "category": category,
                "importance": importance,
                "date": date_str,
                "raw_file": str(raw_file),
            }
            saved = _save_news(payload)
            news_id = saved.get("id")

            collected += 1
            articles.append({
                "id": news_id,
                "headline": headline,
                "source": source,
                "importance": importance,
            })
            print(
                f"[collect_news] saved [{importance}/5] {source}: {headline[:80]}",
                file=sys.stderr,
            )

    return {
        "collected": collected,
        "skipped_dupes": skipped_dupes,
        "articles": articles,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect news articles by category using DuckDuckGo."
    )
    sub = parser.add_subparsers(dest="category", required=True)

    valid_categories = list(CATEGORY_QUERIES.keys()) + ["custom"]
    for cat in valid_categories:
        p = sub.add_parser(cat, help=f"Collect {cat} news.")
        p.add_argument("--limit", type=int, default=5, help="Max results per query (default 5).")
        if cat == "custom":
            p.add_argument("--query", required=True, help="Custom search query string.")
            p.add_argument("--category", dest="custom_category", default="custom",
                           help="Category label to use when saving (default: custom).")

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    env = _load_env()
    category = args.category

    if category == "custom":
        queries = [args.query]
        save_category = args.custom_category
    else:
        queries = CATEGORY_QUERIES[category]
        save_category = category

    result = asyncio.run(_collect(queries, save_category, args.limit, env))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
