"""
research_topic.py — Web research for Writer agent (Scenario 1 only).

Usage:
    python research_topic.py "AI compliance SaaS" --queries 3 --sources_per_query 2
    python research_topic.py "freelancer tax estimation" --output_file workspace/temp/research_ai_compliance.json
"""

import json
import sys
import argparse
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    import httpx
except ImportError:
    print(json.dumps({"error": "httpx is required: pip install httpx"}))
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DDGO_URL = "https://html.duckduckgo.com/html/"
_FETCH_TIMEOUT = 15  # seconds
_MAX_PAGE_CHARS = 5000
_MIN_PARAGRAPH_LEN = 100

_NOISE_DOMAINS = {
    "reddit.com", "www.reddit.com",
    "quora.com", "www.quora.com",
    "pinterest.com", "www.pinterest.com",
    "facebook.com", "www.facebook.com",
    "instagram.com", "www.instagram.com",
    "tiktok.com", "www.tiktok.com",
    "youtube.com", "www.youtube.com",
}

_AUTHORITATIVE_TLDS = {".gov", ".edu", ".org"}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# ---------------------------------------------------------------------------
# Query generation
# ---------------------------------------------------------------------------

def _generate_queries(topic: str, n: int = 4) -> list[str]:
    """Generate targeted search queries from the topic using simple heuristics."""
    templates = [
        topic,
        f"{topic} statistics data",
        f"{topic} examples case study",
        f"{topic} expert opinion",
        f"{topic} trends 2024",
        f"{topic} best practices guide",
    ]
    return templates[:max(1, min(n, len(templates)))]


# ---------------------------------------------------------------------------
# DuckDuckGo scraper
# ---------------------------------------------------------------------------

def _ddgo_search(query: str, max_results: int = 5, client: httpx.Client = None) -> list[dict]:
    """
    POST to DuckDuckGo HTML endpoint and extract result URLs + titles.
    Returns list of {"url": ..., "title": ...}.
    """
    own_client = client is None
    if own_client:
        client = httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=_FETCH_TIMEOUT)

    results = []
    try:
        resp = client.post(_DDGO_URL, data={"q": query, "b": "", "kl": "en-us"})
        resp.raise_for_status()
        html = resp.text

        # Extract result links: DuckDuckGo HTML wraps results in <a class="result__a"> tags
        # Pattern: href="..." class="result__a" or result__url
        link_pattern = re.compile(
            r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        for m in link_pattern.finditer(html):
            raw_url = m.group(1).strip()
            raw_title = re.sub(r"<[^>]+>", "", m.group(2)).strip()

            # DuckDuckGo sometimes uses redirect URLs — extract the real URL
            if raw_url.startswith("//duckduckgo.com/l/?"):
                uddg_match = re.search(r"uddg=([^&]+)", raw_url)
                if uddg_match:
                    from urllib.parse import unquote
                    raw_url = unquote(uddg_match.group(1))

            if not raw_url.startswith("http"):
                continue

            parsed = urlparse(raw_url)
            domain = parsed.netloc.lower()

            # Skip noise domains
            if domain in _NOISE_DOMAINS:
                continue

            results.append({"url": raw_url, "title": raw_title or domain})
            if len(results) >= max_results:
                break

    except Exception:
        pass  # graceful fallback: return what we have
    finally:
        if own_client:
            client.close()

    return results


# ---------------------------------------------------------------------------
# Page fetcher & text extractor
# ---------------------------------------------------------------------------

def _strip_html(html: str) -> str:
    """Strip HTML tags and return plain text."""
    # Remove script/style blocks entirely
    html = re.sub(r"<(script|style|noscript|nav|footer|header)[^>]*>.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    # Remove all remaining tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_paragraphs(text: str, min_len: int = _MIN_PARAGRAPH_LEN) -> list[str]:
    """Split text into meaningful paragraphs."""
    # Split on double whitespace, newlines, or sentence-ending punctuation followed by space
    segments = re.split(r"\s{2,}|\n+", text)
    paragraphs = []
    for seg in segments:
        seg = seg.strip()
        if len(seg) >= min_len:
            paragraphs.append(seg[:500])  # cap individual paragraph length
    return paragraphs


def _fetch_page(url: str, client: httpx.Client) -> dict:
    """
    Fetch a URL and extract text content.
    Returns {"url": ..., "title": ..., "key_excerpts": [...], "fetched": bool}
    """
    result = {"url": url, "title": "", "key_excerpts": [], "fetched": False}
    try:
        resp = client.get(url, timeout=_FETCH_TIMEOUT)
        resp.raise_for_status()
        html = resp.text

        # Extract title
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if title_match:
            result["title"] = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", title_match.group(1))).strip()

        text = _strip_html(html)
        text = text[:_MAX_PAGE_CHARS]  # cap total text

        paragraphs = _extract_paragraphs(text)
        result["key_excerpts"] = paragraphs[:5]  # top 5 meaningful paragraphs
        result["fetched"] = True

    except Exception:
        result["fetched"] = False

    return result


# ---------------------------------------------------------------------------
# Fact/stat/example extractor
# ---------------------------------------------------------------------------

_STAT_PATTERNS = [
    re.compile(r"\b\d+(\.\d+)?\s*%", re.IGNORECASE),
    re.compile(r"\$\s*\d[\d,\.]+\s*(million|billion|trillion|k|M|B)?", re.IGNORECASE),
    re.compile(r"\b\d[\d,\.]+\s*(million|billion|trillion)\b", re.IGNORECASE),
]

_FACT_KEYWORDS = ["according to", "study shows", "research shows", "found that", "reported that", "survey"]
_EXAMPLE_KEYWORDS = ["for example", "case study", "such as", "including", "like", "instance"]


def _extract_signals(excerpts: list[str]) -> dict:
    """Extract facts, statistics, and examples from text excerpts."""
    key_facts: list[str] = []
    statistics: list[str] = []
    examples: list[str] = []

    for excerpt in excerpts:
        lower = excerpt.lower()

        # Statistics
        for pat in _STAT_PATTERNS:
            if pat.search(excerpt):
                statistics.append(excerpt[:200])
                break

        # Facts
        if any(kw in lower for kw in _FACT_KEYWORDS):
            key_facts.append(excerpt[:200])

        # Examples
        if any(kw in lower for kw in _EXAMPLE_KEYWORDS):
            examples.append(excerpt[:200])

    # Deduplicate while preserving order
    def _dedup(lst):
        seen = set()
        out = []
        for item in lst:
            if item not in seen:
                seen.add(item)
                out.append(item)
        return out

    return {
        "key_facts": _dedup(key_facts)[:5],
        "statistics": _dedup(statistics)[:5],
        "examples": _dedup(examples)[:3],
    }


# ---------------------------------------------------------------------------
# Main research function
# ---------------------------------------------------------------------------

def research_topic(
    topic: str,
    n_queries: int = 4,
    sources_per_query: int = 2,
) -> dict:
    """
    Research a topic using DuckDuckGo and page fetching.

    Returns structured research data dict.
    """
    queries = _generate_queries(topic, n_queries)
    all_sources: list[dict] = []
    seen_urls: set[str] = set()
    all_excerpts: list[str] = []

    with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=_FETCH_TIMEOUT) as client:
        for query in queries:
            search_results = _ddgo_search(query, max_results=sources_per_query + 2, client=client)

            fetched_for_query = 0
            for sr in search_results:
                if fetched_for_query >= sources_per_query:
                    break
                url = sr["url"]
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                page_data = _fetch_page(url, client)
                page_data["title"] = page_data["title"] or sr.get("title", "")
                all_sources.append(page_data)
                all_excerpts.extend(page_data.get("key_excerpts", []))

                if page_data["fetched"]:
                    fetched_for_query += 1

    signals = _extract_signals(all_excerpts)

    return {
        "topic": topic,
        "queries_run": queries,
        "sources": all_sources,
        "key_facts": signals["key_facts"],
        "statistics": signals["statistics"],
        "examples": signals["examples"],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Web research for Writer agent (Scenario 1 only)."
    )
    parser.add_argument("topic", help="Research topic string.")
    parser.add_argument(
        "--queries", type=int, default=4, dest="n_queries",
        help="Number of search queries to run (default: 4, max: 6).",
    )
    parser.add_argument(
        "--sources_per_query", type=int, default=2,
        help="Number of pages to fetch per query (default: 2).",
    )
    parser.add_argument(
        "--output_file", type=str, default=None,
        help="Path to save JSON output (relative to cwd or absolute).",
    )
    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    try:
        result = research_topic(
            topic=args.topic,
            n_queries=args.n_queries,
            sources_per_query=args.sources_per_query,
        )

        output_json = json.dumps(result, indent=2, ensure_ascii=False)

        if args.output_file:
            out_path = Path(args.output_file)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(output_json, encoding="utf-8")
            # Also print a summary to stdout
            summary = {
                "topic": result["topic"],
                "queries_run": result["queries_run"],
                "sources_fetched": sum(1 for s in result["sources"] if s["fetched"]),
                "key_facts_found": len(result["key_facts"]),
                "statistics_found": len(result["statistics"]),
                "saved_to": str(out_path.resolve()),
            }
            print(json.dumps(summary, indent=2))
        else:
            print(output_json)

    except Exception as exc:
        print(json.dumps({"error": f"Research failed: {exc}"}))
        sys.exit(1)
