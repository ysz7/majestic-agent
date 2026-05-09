import httpx
import re


async def search(query: str, max_results: int = 5) -> list[dict]:
    """DuckDuckGo instant answers (free, no key needed). Falls back to HTML scraping."""
    url = "https://api.duckduckgo.com/"
    params = {"q": query, "format": "json", "no_redirect": "1", "no_html": "1"}
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(url, params=params)
        data = resp.json()

    results = []
    # RelatedTopics
    for topic in data.get("RelatedTopics", [])[:max_results]:
        if isinstance(topic, dict) and "Text" in topic:
            results.append({
                "title": topic.get("Text", "")[:80],
                "url": topic.get("FirstURL", ""),
                "snippet": topic.get("Text", ""),
            })
    return results[:max_results]
