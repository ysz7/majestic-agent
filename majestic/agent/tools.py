"""
Tool registry for the agentic loop.

Tools return raw text/data — synthesis is done by the loop's LLM, not the tool itself.
Register new tools with the @tool() decorator.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

# ── Registry ─────────────────────────────────────────────────────────────────

@dataclass
class _Tool:
    name: str
    description: str
    input_schema: dict
    fn: Callable

_registry: dict[str, _Tool] = {}


def tool(name: str, description: str, input_schema: dict):
    """Decorator — registers a function as a callable tool."""
    def decorator(fn: Callable) -> Callable:
        _registry[name] = _Tool(name, description, input_schema, fn)
        return fn
    return decorator


def get_schemas() -> list[dict]:
    """Return tool definitions in Anthropic format for LLM tool_use."""
    return [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema}
        for t in _registry.values()
    ]


def execute(name: str, arguments: dict) -> str:
    t = _registry.get(name)
    if not t:
        return f"[tool error] Unknown tool: {name!r}"
    try:
        result = t.fn(**arguments)
        return str(result) if result is not None else "(no output)"
    except Exception as e:
        return f"[tool error] {name}: {e}"


# ── Built-in tools ────────────────────────────────────────────────────────────

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
    from core.rag_engine import _get_db, embed_text, _known_files
    db = _get_db()
    known = _known_files()
    parts: list[str] = []

    # Vector search over documents
    doc_files = [f for f in known if not f.startswith("intel:")]
    if doc_files:
        emb = embed_text(query)
        chunks = db.vector_search_match(emb, k=6)
        for c in chunks:
            parts.append(f"[doc: {c.get('file_name', '')}]\n{c['content']}")

    # FTS5 search over news/intel
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
    from core.web_search import search
    results = search(query, max_results=5)
    if not results:
        return "No web results found."
    parts = []
    for r in results:
        title = r.get("title", "")
        content = r.get("content", "")[:600]
        url = r.get("url", "")
        parts.append(f"[{title}]\n{content}\nSource: {url}")
    return "\n\n---\n\n".join(parts)


@tool(
    name="get_market_data",
    description="Get current cryptocurrency, stock, and forex price snapshot.",
    input_schema={
        "type": "object",
        "properties": {},
    },
)
def get_market_data() -> str:
    try:
        from core.market_pulse import get_snapshot
        data = get_snapshot()
        if not data:
            return "Market data unavailable."
        lines = []
        for section, items in data.items():
            if isinstance(items, dict):
                lines.append(f"\n{section}:")
                for symbol, info in items.items():
                    if isinstance(info, dict):
                        price = info.get("price") or info.get("usd", "?")
                        change = info.get("change_24h") or info.get("change_percent", "")
                        lines.append(f"  {symbol}: {price}" + (f" ({change:+.2f}%)" if isinstance(change, (int, float)) else ""))
        return "\n".join(lines) if lines else str(data)
    except Exception as e:
        return f"Market data error: {e}"
