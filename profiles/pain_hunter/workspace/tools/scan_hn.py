"""
Scan Hacker News for pain points in a given niche.
Uses Algolia HN API (free, no auth): https://hn.algolia.com/api/v1/search
Usage: python scan_hn.py "e-commerce logistics"
Output: saves raw text to output/raw/[niche]/[date]/hackernews.txt, prints JSON summary
"""
import sys, json, asyncio, httpx
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parents[2]  # workspace/
OUTPUT_DIR = BASE_DIR / "output" / "raw"

HN_API_BASE = "https://hn.algolia.com/api/v1"

# Tags to query: comments and Ask HN posts
SEARCH_CONFIGS = [
    # Ask HN posts about the niche (title search)
    {"endpoint": "/search", "params_extra": {"tags": "ask_hn", "hitsPerPage": 20}},
    # Comments mentioning the niche
    {"endpoint": "/search", "params_extra": {"tags": "comment", "hitsPerPage": 30}},
    # Stories mentioning the niche
    {"endpoint": "/search", "params_extra": {"tags": "story", "hitsPerPage": 20}},
]

PAIN_KEYWORDS = [
    "problem", "frustrat", "annoying", "wish", "missing", "broken",
    "painful", "nightmare", "manual", "workaround", "no tool", "feature request",
    "why is there no", "difficult", "impossible", "tedious", "hack",
]


def score_item(item: dict) -> int:
    """Return a relevance score based on pain signals in text."""
    text = " ".join([
        item.get("title") or "",
        item.get("comment_text") or "",
        item.get("story_text") or "",
    ]).lower()
    score = item.get("points") or 0
    for kw in PAIN_KEYWORDS:
        if kw in text:
            score += 2
    return score


async def fetch_hn_items(niche: str, endpoint: str, params_extra: dict) -> list[dict]:
    """Fetch items from Algolia HN API."""
    params = {"query": niche, "hitsPerPage": params_extra.get("hitsPerPage", 20)}
    if "tags" in params_extra:
        params["tags"] = params_extra["tags"]

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        try:
            resp = await client.get(f"{HN_API_BASE}{endpoint}", params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("hits", [])
        except Exception:
            return []


def format_item(item: dict) -> str:
    """Format an HN item into readable text."""
    parts = []
    item_id = item.get("objectID", "")
    url = f"https://news.ycombinator.com/item?id={item_id}"

    title = item.get("title") or item.get("story_title") or "(no title)"
    points = item.get("points") or 0
    author = item.get("author") or "unknown"
    created = item.get("created_at") or ""
    comment_text = item.get("comment_text") or ""
    story_text = item.get("story_text") or ""

    parts.append(f"URL: {url}")
    parts.append(f"Title: {title}")
    parts.append(f"Points: {points}  Author: {author}  Date: {created[:10] if created else ''}")

    if comment_text:
        # Strip HTML tags
        import re
        text = re.sub(r'<[^>]+>', ' ', comment_text)
        text = re.sub(r'\s+', ' ', text).strip()
        parts.append(f"Comment: {text[:1000]}")
    if story_text:
        import re
        text = re.sub(r'<[^>]+>', ' ', story_text)
        text = re.sub(r'\s+', ' ', text).strip()
        parts.append(f"Text: {text[:1000]}")

    return "\n".join(parts)


async def scan(niche: str) -> dict:
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    out_dir = OUTPUT_DIR / niche.replace(" ", "_") / date_str
    out_dir.mkdir(parents=True, exist_ok=True)

    # Fetch from all search configs concurrently
    tasks = [
        fetch_hn_items(niche, cfg["endpoint"], cfg["params_extra"])
        for cfg in SEARCH_CONFIGS
    ]
    results_nested = await asyncio.gather(*tasks, return_exceptions=True)

    all_items: list[dict] = []
    seen_ids: set = set()
    for batch in results_nested:
        if isinstance(batch, Exception):
            continue
        for item in batch:
            item_id = item.get("objectID")
            if item_id and item_id not in seen_ids:
                seen_ids.add(item_id)
                all_items.append(item)

    # Filter: keep items with points > 5 OR strong pain signal keywords
    filtered = [
        item for item in all_items
        if (item.get("points") or 0) > 5 or score_item(item) >= 4
    ]

    # Sort by score descending
    filtered.sort(key=score_item, reverse=True)

    raw_content = []
    for item in filtered[:50]:
        raw_content.append(format_item(item))

    combined = ("\n" + "=" * 60 + "\n").join(raw_content)
    out_file = out_dir / "hackernews.txt"
    out_file.write_text(combined, encoding="utf-8")

    return {
        "niche": niche,
        "date": date_str,
        "items_found": len(filtered),
        "output_file": str(out_file),
        "content_length": len(combined),
    }


if __name__ == "__main__":
    niche = sys.argv[1] if len(sys.argv) > 1 else "e-commerce logistics"
    result = asyncio.run(scan(niche))
    print(json.dumps(result, indent=2))
