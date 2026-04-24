"""
Universal search across all databases with RRF (Reciprocal Rank Fusion).

Searches: news_fts, messages_fts, vectors — merges results by rank.
"""
from majestic.tools.registry import tool

_RRF_K = 60  # RRF constant


def _rrf_score(rank: int) -> float:
    return 1.0 / (_RRF_K + rank + 1)


def _rrf_merge(*ranked_lists: list[dict], key: str = "id") -> list[dict]:
    """Merge multiple ranked result lists using RRF. Each list is [{key, ...}]."""
    scores: dict = {}
    items:  dict = {}
    for result_list in ranked_lists:
        for rank, item in enumerate(result_list):
            k = item.get(key) or id(item)
            scores[k] = scores.get(k, 0.0) + _rrf_score(rank)
            items[k]  = item
    return [items[k] for k in sorted(scores, key=scores.__getitem__, reverse=True)]


@tool(
    name="db_search",
    description=(
        "Search across all databases: news, conversation history, and indexed documents. "
        "Results from all sources are merged by relevance using RRF. "
        "Use this when you need information that may exist in any source."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query",
            },
            "sources": {
                "type": "string",
                "enum": ["all", "news", "messages", "docs"],
                "description": "Which sources to search (default: all)",
            },
        },
        "required": ["query"],
    },
)
def db_search(query: str, sources: str = "all") -> str:
    from majestic.db.state import StateDB
    db = StateDB()

    news_results: list[dict] = []
    msg_results:  list[dict] = []
    vec_results:  list[dict] = []

    if sources in ("all", "news"):
        try:
            news_results = db.search_news(query, k=8)
        except Exception:
            pass

    if sources in ("all", "messages"):
        try:
            msg_results = db.search_messages(query, k=8)
        except Exception:
            pass

    if sources in ("all", "docs"):
        try:
            from core.rag_engine import embed_text
            emb = embed_text(query)
            raw = db.vector_search_match(emb, k=8)
            vec_results = [{"id": f"vec:{i}", **r} for i, r in enumerate(raw)]
        except Exception:
            pass

    # Merge with RRF
    merged = _rrf_merge(
        [{"id": f"news:{r['id']}", **r} for r in news_results],
        [{"id": f"msg:{r['id']}",  **r} for r in msg_results],
        vec_results,
    )

    if not merged:
        return "No results found."

    parts: list[str] = []
    for item in merged[:10]:
        if item.get("title"):
            src = item.get("source", "news")
            parts.append(f"[{src}] {item['title']}\n{item.get('description','')}")
        elif item.get("content"):
            role = item.get("role", "")
            parts.append(f"[{role}] {item['content'][:300]}")
        elif item.get("chunk") or item.get("text"):
            text = item.get("chunk") or item.get("text", "")
            parts.append(f"[doc] {text[:300]}")

    return "\n\n---\n\n".join(parts) if parts else "No readable results found."
