"""
Scan Product Hunt and AlternativeTo for pain points in a given niche.
Uses DuckDuckGo search for site:producthunt.com and site:alternativeto.net queries.
Usage: python scan_producthunt.py "e-commerce logistics"
Output: saves raw text to output/raw/[niche]/[date]/producthunt.txt, prints JSON summary
"""
import sys, json, asyncio, httpx, re
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parents[2]  # workspace/
OUTPUT_DIR = BASE_DIR / "output" / "raw"

QUERY_TEMPLATES = [
    # Product Hunt: users expressing wishes/missing features in comments
    'site:producthunt.com "{niche}" "would love" OR "missing"',
    'site:producthunt.com "{niche}" "wish" OR "please add" OR "feature request"',
    'site:producthunt.com "{niche}" "not possible" OR "workaround" OR "frustrating"',
    'site:producthunt.com "{niche}" "when will" OR "why can\'t" OR "need this"',
    # AlternativeTo: dissatisfied users looking for alternatives
    'site:alternativeto.net "{niche}" "alternative" "not good" OR "missing" OR "hate"',
    'site:alternativeto.net "{niche}" "looking for" OR "switched" OR "moved away"',
]

PAIN_SIGNALS = [
    "wish", "missing", "would love", "frustrat", "annoying", "pain",
    "workaround", "hack", "not possible", "why can't", "when will",
    "switched", "moved away", "looking for", "hate", "please add",
]


def has_pain_signal(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in PAIN_SIGNALS)


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


async def fetch_page(url: str) -> str:
    """Fetch page and return clean text."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html",
    }
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers=headers)
            text = re.sub(r'<[^>]+>', ' ', resp.text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:5000]
        except Exception:
            return ""


def is_valid_url(url: str) -> bool:
    return "producthunt.com" in url or "alternativeto.net" in url


async def scan(niche: str) -> dict:
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    out_dir = OUTPUT_DIR / niche.replace(" ", "_") / date_str
    out_dir.mkdir(parents=True, exist_ok=True)

    all_results = []
    for template in QUERY_TEMPLATES:
        query = template.format(niche=niche)
        results = await search_ddg(query, max_results=4)
        all_results.extend(results)

    # Collect unique valid URLs
    seen_urls: set = set()
    valid_results = []
    for r in all_results:
        url = r.get("url", "")
        if url and url not in seen_urls and is_valid_url(url):
            seen_urls.add(url)
            valid_results.append(r)
            if len(valid_results) >= 15:
                break

    # Fetch pages concurrently
    pages = await asyncio.gather(
        *[fetch_page(r["url"]) for r in valid_results],
        return_exceptions=True,
    )

    raw_content = []
    for r, page_content in zip(valid_results, pages):
        if isinstance(page_content, Exception) or not page_content:
            continue
        snippet = r.get("snippet", "")
        source_type = "ProductHunt" if "producthunt.com" in r["url"] else "AlternativeTo"

        # Prioritize pages with pain signals in snippet or content
        combined_text = snippet + " " + page_content
        pain_flag = "[PAIN SIGNAL]" if has_pain_signal(combined_text) else ""

        raw_content.append(
            f"SOURCE [{source_type}]{pain_flag}: {r['url']}\n"
            f"Snippet: {snippet}\n"
            f"Page Content:\n{page_content}\n"
            f"{'='*60}"
        )

    # Sort: pain-signal entries first
    raw_content.sort(key=lambda x: 0 if "[PAIN SIGNAL]" in x else 1)

    combined = "\n\n".join(raw_content)
    out_file = out_dir / "producthunt.txt"
    out_file.write_text(combined, encoding="utf-8")

    ph_count = sum(1 for r in valid_results if "producthunt.com" in r.get("url", ""))
    alt_count = sum(1 for r in valid_results if "alternativeto.net" in r.get("url", ""))

    return {
        "niche": niche,
        "date": date_str,
        "urls_fetched": len(raw_content),
        "producthunt_urls": ph_count,
        "alternativeto_urls": alt_count,
        "output_file": str(out_file),
        "content_length": len(combined),
    }


if __name__ == "__main__":
    niche = sys.argv[1] if len(sys.argv) > 1 else "e-commerce logistics"
    result = asyncio.run(scan(niche))
    print(json.dumps(result, indent=2))
