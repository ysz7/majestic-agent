"""
Scan Indie Hackers for pain points in a given niche.
Uses DuckDuckGo search for site:indiehackers.com queries.
Focus: interview "what problem did you solve?" sections, forum complaints, product posts.
Usage: python scan_indiehackers.py "e-commerce logistics"
Output: saves raw text to output/raw/[niche]/[date]/indiehackers.txt, prints JSON summary
"""
import sys, json, asyncio, httpx, re
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parents[2]  # workspace/
OUTPUT_DIR = BASE_DIR / "output" / "raw"

QUERY_TEMPLATES = [
    # General niche pain/frustration mentions
    'site:indiehackers.com "{niche}" problem OR frustration',
    'site:indiehackers.com "{niche}" "pain point" OR "biggest challenge"',
    # Interview-style: problem validation and origin stories
    'site:indiehackers.com "{niche}" "problem I solved" OR "problem we solved"',
    'site:indiehackers.com "{niche}" "noticed that" OR "realized that" problem',
    # Forum threads about gaps/missing tools
    'site:indiehackers.com "{niche}" "no good tool" OR "manually" OR "workaround"',
    'site:indiehackers.com "{niche}" "wish there was" OR "is there a tool"',
    # Validation / market research posts
    'site:indiehackers.com "{niche}" "validating" OR "idea" OR "looking for feedback"',
]

PAIN_KEYWORDS = [
    "problem", "frustrat", "pain point", "biggest challenge", "annoying",
    "manually", "workaround", "no good tool", "wish there was", "is there a tool",
    "noticed that", "realized that", "waste of time", "tedious", "difficult",
    "nightmare", "broken", "missing", "gap in the market",
]

INTERVIEW_SIGNALS = [
    "what was the problem", "problem i solved", "problem we solved",
    "why did you build", "what inspired you", "noticed that",
]


def score_text(text: str) -> int:
    """Score text by pain signal count and interview signal presence."""
    text_lower = text.lower()
    score = sum(1 for kw in PAIN_KEYWORDS if kw in text_lower)
    # Bonus for interview-style content (higher signal density)
    score += sum(2 for kw in INTERVIEW_SIGNALS if kw in text_lower)
    return score


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


def classify_page_type(url: str) -> str:
    """Classify IH page type based on URL pattern."""
    if "/interviews/" in url:
        return "interview"
    if "/products/" in url:
        return "product"
    if "/posts/" in url or "/forum/" in url:
        return "forum"
    return "general"


async def fetch_ih_page(url: str) -> str:
    """Fetch an Indie Hackers page and extract relevant content."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html",
    }
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers=headers)
            text = resp.text

            # Try to extract structured content
            # IH interviews often have Q&A format
            qa_sections = re.findall(
                r'<[^>]*class="[^"]*question[^"]*"[^>]*>(.*?)</[^>]+>'
                r'|<[^>]*class="[^"]*answer[^"]*"[^>]*>(.*?)</[^>]+>',
                text, re.DOTALL
            )

            # Extract article/post body text
            article_match = re.search(
                r'<article[^>]*>(.*?)</article>|<div[^>]*class="[^"]*content[^"]*"[^>]*>(.*?)</div>',
                text, re.DOTALL
            )

            if qa_sections or article_match:
                parts = []
                for q, a in qa_sections[:10]:
                    raw = q or a
                    clean = re.sub(r'<[^>]+>', ' ', raw)
                    clean = re.sub(r'\s+', ' ', clean).strip()
                    if len(clean) > 30:
                        parts.append(clean[:500])
                if article_match:
                    raw_body = article_match.group(1) or article_match.group(2) or ""
                    clean_body = re.sub(r'<[^>]+>', ' ', raw_body)
                    clean_body = re.sub(r'\s+', ' ', clean_body).strip()
                    parts.append(clean_body[:3000])
                return "\n---\n".join(parts)[:5000]

            # Fallback: strip all HTML
            raw = re.sub(r'<[^>]+>', ' ', text)
            raw = re.sub(r'\s+', ' ', raw).strip()
            return raw[:5000]
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

    # Collect unique IH URLs
    seen_urls: set = set()
    valid_results = []
    for r in all_results:
        url = r.get("url", "")
        if url and url not in seen_urls and "indiehackers.com" in url:
            seen_urls.add(url)
            valid_results.append(r)
            if len(valid_results) >= 15:
                break

    # Fetch pages concurrently
    pages = await asyncio.gather(
        *[fetch_ih_page(r["url"]) for r in valid_results],
        return_exceptions=True,
    )

    # Build entries with pain scores
    entries = []
    for r, page_content in zip(valid_results, pages):
        if isinstance(page_content, Exception) or not page_content:
            continue
        snippet = r.get("snippet", "")
        combined_text = snippet + " " + page_content
        pain_score = score_text(combined_text)
        page_type = classify_page_type(r["url"])
        entries.append({
            "url": r["url"],
            "snippet": snippet,
            "content": page_content,
            "pain_score": pain_score,
            "page_type": page_type,
        })

    # Sort: interviews first (highest signal), then by pain score
    entries.sort(key=lambda x: (0 if x["page_type"] == "interview" else 1, -x["pain_score"]))

    raw_content = []
    for entry in entries:
        type_label = entry["page_type"].upper()
        pain_label = f"[PAIN SCORE: {entry['pain_score']}]" if entry["pain_score"] > 0 else ""
        raw_content.append(
            f"SOURCE [{type_label}]{pain_label}: {entry['url']}\n"
            f"Snippet: {entry['snippet']}\n"
            f"Content:\n{entry['content']}\n"
            f"{'='*60}"
        )

    combined = "\n\n".join(raw_content)
    out_file = out_dir / "indiehackers.txt"
    out_file.write_text(combined, encoding="utf-8")

    interview_count = sum(1 for e in entries if e["page_type"] == "interview")
    high_pain = sum(1 for e in entries if e["pain_score"] >= 3)

    return {
        "niche": niche,
        "date": date_str,
        "urls_fetched": len(entries),
        "interview_pages": interview_count,
        "high_pain_signal_urls": high_pain,
        "output_file": str(out_file),
        "content_length": len(combined),
    }


if __name__ == "__main__":
    niche = sys.argv[1] if len(sys.argv) > 1 else "e-commerce logistics"
    result = asyncio.run(scan(niche))
    print(json.dumps(result, indent=2))
