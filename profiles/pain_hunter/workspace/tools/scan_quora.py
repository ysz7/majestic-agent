"""
Scan Quora for pain points in a given niche.
Uses DuckDuckGo search for site:quora.com queries.
Pain signals: questions = unmet needs; workaround answers = active pain.
Usage: python scan_quora.py "e-commerce logistics"
Output: saves raw text to output/raw/[niche]/[date]/quora.txt, prints JSON summary
"""
import sys, json, asyncio, httpx, re
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parents[2]  # workspace/
OUTPUT_DIR = BASE_DIR / "output" / "raw"

QUERY_TEMPLATES = [
    # Question-form pain signals (questions = unmet needs)
    'site:quora.com "why is there no" "{niche}"',
    'site:quora.com "why doesn\'t" "{niche}" tool OR software OR solution',
    'site:quora.com "{niche}" "best way to" OR "how do you" problem',
    'site:quora.com "{niche}" "is there a tool" OR "is there software"',
    'site:quora.com "{niche}" "manually" OR "workaround" OR "hack"',
    # Frustration/pain signals in answers
    'site:quora.com "{niche}" "biggest problem" OR "main challenge" OR "pain point"',
    'site:quora.com "{niche}" "frustrated with" OR "annoying" OR "nightmare"',
]

PAIN_KEYWORDS = [
    "why is there no", "why doesn't", "manually", "workaround", "hack",
    "frustrated", "annoying", "nightmare", "pain point", "biggest problem",
    "no good solution", "wish there was", "looking for", "can't find",
    "difficult", "tedious", "waste of time", "biggest challenge",
]


def score_text(text: str) -> int:
    """Score text by number of pain signal keywords."""
    text_lower = text.lower()
    return sum(1 for kw in PAIN_KEYWORDS if kw in text_lower)


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


async def fetch_quora_page(url: str) -> str:
    """Fetch a Quora page and extract question + answer text."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html",
    }
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers=headers)
            text = resp.text

            # Try to extract question title (Quora uses various patterns)
            question_match = re.search(
                r'<h1[^>]*>(.*?)</h1>|"questionText"\s*:\s*"([^"]+)"', text, re.DOTALL
            )
            question = ""
            if question_match:
                raw_q = question_match.group(1) or question_match.group(2) or ""
                question = re.sub(r'<[^>]+>', '', raw_q).strip()

            # Extract answer snippets
            # Quora embeds text in various span/div structures
            answer_matches = re.findall(
                r'"text"\s*:\s*"((?:[^"\\]|\\.){{50,500}})"', text
            )
            answers = []
            for a in answer_matches[:10]:
                cleaned = a.replace("\\n", " ").replace('\\"', '"').strip()
                if len(cleaned) > 50:
                    answers.append(cleaned[:600])

            # Fallback to full HTML strip
            if not question and not answers:
                raw = re.sub(r'<[^>]+>', ' ', text)
                raw = re.sub(r'\s+', ' ', raw).strip()
                return raw[:5000]

            parts = []
            if question:
                parts.append(f"Question: {question}")
            if answers:
                parts.append("Answers:\n" + "\n---\n".join(answers[:5]))
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

    # Collect unique Quora URLs
    seen_urls: set = set()
    valid_results = []
    for r in all_results:
        url = r.get("url", "")
        if url and url not in seen_urls and "quora.com" in url:
            seen_urls.add(url)
            valid_results.append(r)
            if len(valid_results) >= 15:
                break

    # Fetch pages concurrently
    pages = await asyncio.gather(
        *[fetch_quora_page(r["url"]) for r in valid_results],
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
        entries.append({
            "url": r["url"],
            "snippet": snippet,
            "content": page_content,
            "pain_score": pain_score,
        })

    # Sort by pain score descending
    entries.sort(key=lambda x: x["pain_score"], reverse=True)

    raw_content = []
    for entry in entries:
        pain_label = f"[PAIN SCORE: {entry['pain_score']}]" if entry["pain_score"] > 0 else ""
        raw_content.append(
            f"SOURCE{pain_label}: {entry['url']}\n"
            f"Snippet: {entry['snippet']}\n"
            f"Content:\n{entry['content']}\n"
            f"{'='*60}"
        )

    combined = "\n\n".join(raw_content)
    out_file = out_dir / "quora.txt"
    out_file.write_text(combined, encoding="utf-8")

    high_pain = sum(1 for e in entries if e["pain_score"] >= 2)

    return {
        "niche": niche,
        "date": date_str,
        "urls_fetched": len(entries),
        "high_pain_signal_urls": high_pain,
        "output_file": str(out_file),
        "content_length": len(combined),
    }


if __name__ == "__main__":
    niche = sys.argv[1] if len(sys.argv) > 1 else "e-commerce logistics"
    result = asyncio.run(scan(niche))
    print(json.dumps(result, indent=2))
