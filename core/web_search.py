"""
Real-time web search — DuckDuckGo (free, no key) + Tavily (optional, higher quality).

Priority:
  1. Tavily if TAVILY_API_KEY is set in .env
  2. DuckDuckGo otherwise (always available, no key needed)

No tool_call required — search logic is handled programmatically.

Usage:
  from core.web_search import search, search_and_answer, is_available
  results = search("WCAG 2.2 accessibility standard")
"""

import os
from typing import Optional

from dotenv import load_dotenv
load_dotenv()


def is_available() -> bool:
    """Always True — DuckDuckGo requires no key."""
    return True


def _search_tavily(query: str, max_results: int) -> list[dict]:
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
        resp = client.search(
            query=query,
            search_depth="basic",
            max_results=max_results,
            include_answer=False,
        )
        return [
            {
                "title":   r.get("title", ""),
                "url":     r.get("url", ""),
                "content": r.get("content", "")[:1000],
            }
            for r in resp.get("results", [])
        ]
    except Exception as e:
        from core.error_logger import log_error
        log_error("web_search.tavily", f"Tavily search failed: {query[:60]}", str(e))
        return []


def _search_ddg(query: str, max_results: int) -> list[dict]:
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results))
        return [
            {
                "title":   r.get("title", ""),
                "url":     r.get("href", ""),
                "content": r.get("body", "")[:1000],
            }
            for r in raw
        ]
    except Exception as e:
        from core.error_logger import log_error
        log_error("web_search.ddg", f"DDG search failed: {query[:60]}", str(e))
        return []


def search(query: str, max_results: int = 5) -> list[dict]:
    """
    Search the web. Uses Tavily if API key is set, otherwise DuckDuckGo.
    Returns list of {title, url, content}.
    """
    if os.getenv("TAVILY_API_KEY", "").strip():
        results = _search_tavily(query, max_results)
        if results:
            return results
    return _search_ddg(query, max_results)


def search_and_answer(query: str, max_results: int = 5) -> Optional[dict]:
    """
    Search the web and synthesize an answer using LLM.
    Returns {answer, sources} or None on failure.
    """
    results = search(query, max_results=max_results)
    if not results:
        return None

    context_parts = []
    for r in results:
        context_parts.append(
            f"[{r['title']}]\n{r['content']}\nSource: {r['url']}"
        )
    context = "\n\n---\n\n".join(context_parts)

    from core.rag_engine import llm
    from core.config import get_lang
    from langchain_core.messages import HumanMessage

    lang = get_lang()
    prompt = (
        f"You are a helpful assistant. Answer the question using ONLY the web search results below.\n"
        f"Respond in {lang}. Be concise and accurate. Cite sources where relevant.\n\n"
        f"Search results:\n{context}\n\n"
        f"Question: {query}\n\n"
        f"Answer:"
    )

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        from core.token_tracker import track_response
        track_response(response, "web_search.answer")
        sources = [r["url"] for r in results if r.get("url")]
        return {"answer": response.content, "sources": sources}
    except Exception as e:
        from core.error_logger import log_error
        log_error("web_search.answer", "LLM synthesis failed", str(e))
        return None
