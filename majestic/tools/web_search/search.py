async def search(query: str, max_results: int = 5, brave_api_key: str = "") -> list[dict]:
    """
    Try Brave Search API first (if key configured), fallback to DuckDuckGo.
    Returns [{"title", "url", "snippet"}]
    """
    if brave_api_key:
        try:
            from .providers.brave import search as brave_search
            return await brave_search(query, max_results, brave_api_key)
        except Exception:
            pass
    from .providers.duckduckgo import search as ddg_search
    return await ddg_search(query, max_results)


def tool_schema() -> dict:
    return {
        "name": "web_search",
        "description": "Search the web for information. Returns list of results with title, url, snippet.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {
                    "type": "integer",
                    "description": "Max results to return",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    }
