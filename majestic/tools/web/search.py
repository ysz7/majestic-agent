"""Web and knowledge-base search tools."""
from majestic.tools.registry import tool


@tool(
    name="search_knowledge",
    description="Search indexed local documents and collected research intel for relevant information.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query"},
        },
        "required": ["query"],
    },
)
def search_knowledge(query: str) -> str:
    from majestic.db.state import StateDB
    db = StateDB()
    parts: list[str] = []

    chunks = db.semantic_search(query, k=6)
    for c in chunks:
        parts.append(f"[doc: {c.get('file_name', '')}]\n{c['content']}")

    news = db.search_news(query, k=5)
    for r in news:
        parts.append(f"[intel: {r['source']}] {r['title']}\n{r.get('description', '')}")

    if not parts:
        return "No relevant information found in knowledge base."
    return "\n\n---\n\n".join(parts[:8])


@tool(
    name="search_web",
    description="Search the internet for current news, facts, or information not in the knowledge base.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
        },
        "required": ["query"],
    },
)
def search_web(query: str) -> str:
    from majestic.tools.web.websearch import search
    results = search(query, max_results=5)
    if not results:
        return "No web results found."
    parts = []
    for r in results:
        title   = r.get("title", "")
        content = r.get("content", "")[:600]
        url     = r.get("url", "")
        parts.append(f"[{title}]\n{content}\nSource: {url}")
    return "\n\n---\n\n".join(parts)
