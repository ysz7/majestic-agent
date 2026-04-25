"""Web search — DuckDuckGo (free) or Tavily (optional, higher quality)."""
from __future__ import annotations

import os


def search(query: str, max_results: int = 5) -> list[dict]:
    """Search the web. Returns list of {title, url, content}."""
    if os.getenv("TAVILY_API_KEY", "").strip():
        results = _tavily(query, max_results)
        if results:
            return results
    return _ddg(query, max_results)


def _tavily(query: str, max_results: int) -> list[dict]:
    try:
        from tavily import TavilyClient
        resp = TavilyClient(api_key=os.getenv("TAVILY_API_KEY")).search(
            query=query, search_depth="basic", max_results=max_results, include_answer=False,
        )
        return [
            {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")[:1000]}
            for r in resp.get("results", [])
        ]
    except Exception:
        return []


def _ddg(query: str, max_results: int) -> list[dict]:
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results))
        return [
            {"title": r.get("title", ""), "url": r.get("href", ""), "content": r.get("body", "")[:1000]}
            for r in raw
        ]
    except Exception:
        return []
