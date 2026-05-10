"""
Scan Reddit for pain points in a given niche.
Uses Google search with site:reddit.com queries.
Usage: python scan_reddit.py "e-commerce logistics"
Output: saves raw text to output/raw/[niche]/[date]/reddit.txt, prints JSON summary
"""
import sys, json, asyncio, httpx, re
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parents[2]  # workspace/
OUTPUT_DIR = BASE_DIR / "output" / "raw"

QUERY_TEMPLATES = [
    'site:reddit.com "{niche}" "wish there was"',
    'site:reddit.com "{niche}" "no good solution" OR "manually every week"',
    'site:reddit.com "{niche}" "drives me crazy" OR "nightmare" OR "workaround"',
    'site:reddit.com "{niche}" "is there a tool" OR "why is there no"',
    'site:reddit.com "{niche}" frustrating OR "pain point" OR "annoying"',
]


async def search_ddg(query: str, max_results: int = 5) -> list[dict]:
    """Use DuckDuckGo HTML search as free fallback."""
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
            # Extract result links and snippets from HTML
            link_pattern = re.compile(r'class="result__url"[^>]*>([^<]+)<')
            snippet_pattern = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL)
            href_pattern = re.compile(r'class="result__a"[^>]*href="([^"]+)"')

            hrefs = href_pattern.findall(resp.text)
            snippets_raw = snippet_pattern.findall(resp.text)

            for i, href in enumerate(hrefs[:max_results]):
                # DDG wraps URLs; extract the actual URL from uddg param
                uddg_match = re.search(r'uddg=([^&"]+)', href)
                actual_url = uddg_match.group(1) if uddg_match else href
                # URL-decode
                actual_url = actual_url.replace("%3A", ":").replace("%2F", "/").replace("%3F", "?").replace("%3D", "=").replace("%26", "&")
                snippet = ""
                if i < len(snippets_raw):
                    snippet = re.sub(r'<[^>]+>', ' ', snippets_raw[i]).strip()
                results.append({"url": actual_url, "snippet": snippet})
            return results
        except Exception:
            return []


async def fetch_page(url: str) -> str:
    """Fetch page and return clean text (simplified)."""
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            text = re.sub(r'<[^>]+>', ' ', resp.text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:5000]
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
    seen_urls = set()
    for r in all_results[:15]:
        url = r.get("url", "")
        if url and url not in seen_urls and "reddit.com" in url:
            seen_urls.add(url)
            content = await fetch_page(url)
            if content:
                raw_content.append(f"SOURCE: {url}\n{content}\n{'='*60}")

    combined = "\n\n".join(raw_content)
    out_file = out_dir / "reddit.txt"
    out_file.write_text(combined, encoding="utf-8")

    return {
        "niche": niche,
        "date": date_str,
        "urls_fetched": len(raw_content),
        "output_file": str(out_file),
        "content_length": len(combined),
    }


if __name__ == "__main__":
    niche = sys.argv[1] if len(sys.argv) > 1 else "e-commerce logistics"
    result = asyncio.run(scan(niche))
    print(json.dumps(result, indent=2))
