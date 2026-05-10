"""
Scan GitHub Issues for pain points in a given niche.
Uses DuckDuckGo search for site:github.com queries targeting issue pages.
Usage: python scan_github.py "e-commerce logistics"
Output: saves raw text to output/raw/[niche]/[date]/github.txt, prints JSON summary
"""
import sys, json, asyncio, httpx, re
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parents[2]  # workspace/
OUTPUT_DIR = BASE_DIR / "output" / "raw"

QUERY_TEMPLATES = [
    'site:github.com "{niche}" issues "feature request"',
    'site:github.com "{niche}" issues "pain point" OR "frustrating"',
    'site:github.com "{niche}" issues "missing feature" OR "would love"',
    'site:github.com "{niche}" issues "workaround" OR "not possible"',
    'site:github.com "{niche}" issues "wish" OR "why is there no"',
]


async def search_ddg(query: str, max_results: int = 5) -> list[dict]:
    """Use DuckDuckGo HTML search."""
    url = "https://html.duckduckgo.com/html/"
    params = {"q": query}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
    }
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        try:
            resp = await client.post(url, data=params, headers=headers)
            results = []
            href_pattern = re.compile(r'class="result__a"[^>]*href="([^"]+)"')
            snippet_pattern = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL)

            hrefs = href_pattern.findall(resp.text)
            snippets_raw = snippet_pattern.findall(resp.text)

            for i, href in enumerate(hrefs[:max_results]):
                uddg_match = re.search(r'uddg=([^&"]+)', href)
                actual_url = uddg_match.group(1) if uddg_match else href
                actual_url = (actual_url
                              .replace("%3A", ":").replace("%2F", "/")
                              .replace("%3F", "?").replace("%3D", "=")
                              .replace("%26", "&").replace("%2B", "+"))
                snippet = ""
                if i < len(snippets_raw):
                    snippet = re.sub(r'<[^>]+>', ' ', snippets_raw[i]).strip()
                results.append({"url": actual_url, "snippet": snippet})
            return results
        except Exception:
            return []


def is_github_issue_url(url: str) -> bool:
    """Check if URL points to a GitHub issue or issues list."""
    return "github.com" in url and ("/issues" in url or "/issue/" in url)


async def fetch_github_page(url: str) -> str:
    """Fetch a GitHub issue page and extract relevant text."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html",
    }
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers=headers)
            text = resp.text

            # Try to extract issue title and body
            title_match = re.search(r'<h1[^>]*class="[^"]*gh-header-title[^"]*"[^>]*>(.*?)</h1>', text, re.DOTALL)
            title = ""
            if title_match:
                title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()

            # Extract comment bodies
            comments = re.findall(r'class="[^"]*comment-body[^"]*"[^>]*>(.*?)</div>', text, re.DOTALL)
            comment_texts = []
            for c in comments[:5]:
                clean = re.sub(r'<[^>]+>', ' ', c)
                clean = re.sub(r'\s+', ' ', clean).strip()
                if len(clean) > 50:
                    comment_texts.append(clean[:800])

            # Fallback: strip all HTML
            if not title and not comment_texts:
                raw = re.sub(r'<[^>]+>', ' ', text)
                raw = re.sub(r'\s+', ' ', raw).strip()
                return raw[:5000]

            parts = []
            if title:
                parts.append(f"Issue Title: {title}")
            if comment_texts:
                parts.append("Comments:\n" + "\n---\n".join(comment_texts))
            return "\n".join(parts)[:5000]
        except Exception:
            return ""


async def scan(niche: str) -> dict:
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    out_dir = OUTPUT_DIR / niche.replace(" ", "_") / date_str
    out_dir.mkdir(parents=True, exist_ok=True)

    all_results = []
    for template in QUERY_TEMPLATES:
        query = template.format(niche=niche)
        results = await search_ddg(query, max_results=3)
        all_results.extend(results)

    raw_content = []
    seen_urls: set = set()
    fetch_tasks = []
    valid_results = []

    for r in all_results:
        url = r.get("url", "")
        if url and url not in seen_urls and is_github_issue_url(url):
            seen_urls.add(url)
            valid_results.append(r)
            if len(valid_results) >= 10:
                break

    # Fetch pages concurrently
    async with asyncio.TaskGroup() if sys.version_info >= (3, 11) else _dummy_context() as _:
        pass

    pages = await asyncio.gather(
        *[fetch_github_page(r["url"]) for r in valid_results],
        return_exceptions=True,
    )

    for r, page_content in zip(valid_results, pages):
        if isinstance(page_content, Exception) or not page_content:
            continue
        snippet = r.get("snippet", "")
        raw_content.append(
            f"SOURCE: {r['url']}\n"
            f"Snippet: {snippet}\n"
            f"{page_content}\n"
            f"{'='*60}"
        )

    combined = "\n\n".join(raw_content)
    out_file = out_dir / "github.txt"
    out_file.write_text(combined, encoding="utf-8")

    return {
        "niche": niche,
        "date": date_str,
        "urls_fetched": len(raw_content),
        "output_file": str(out_file),
        "content_length": len(combined),
    }


class _dummy_context:
    """Fallback for Python < 3.11 that lacks TaskGroup."""
    async def __aenter__(self):
        return self
    async def __aexit__(self, *_):
        pass


if __name__ == "__main__":
    niche = sys.argv[1] if len(sys.argv) > 1 else "e-commerce logistics"
    result = asyncio.run(scan(niche))
    print(json.dumps(result, indent=2))
