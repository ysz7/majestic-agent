"""
history_search — search past conversations with FTS5 + LLM summarization.
"""
from majestic.tools.registry import tool

_SUMMARIZE_PROMPT = """\
A user searched for: "{query}"

Here are matching conversation excerpts from past sessions:

{context}

Summarize what was discussed in 2-4 sentences. Focus on key findings, decisions, or answers from those conversations.\
"""


@tool(
    name="history_search",
    description=(
        "Search past conversations by keyword or topic. "
        "Returns a summary of what was discussed in matching sessions. "
        "Use when the user asks 'what did we discuss about X' or 'do you remember when I asked about Y'."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Topic or keywords to search for"},
        },
        "required": ["query"],
    },
)
def history_search(query: str) -> str:
    from majestic.db.state import StateDB
    db = StateDB()
    sessions = db.search_messages_grouped(query, k=5)
    if not sessions:
        return "No matching conversations found."

    parts: list[str] = []
    for s in sessions:
        date = (s.get("started_at") or "")[:10]
        title = s.get("title") or ""
        header = f"[{date}]" + (f" {title}" if title else "")
        snippets = "\n".join(
            f"  {sn['role']}: {sn['content'][:200]}"
            for sn in s.get("snippets", [])
        )
        parts.append(f"{header}\n{snippets}")

    context = "\n\n---\n\n".join(parts)

    try:
        from majestic.llm import get_provider
        prompt = _SUMMARIZE_PROMPT.format(query=query, context=context)
        resp = get_provider().complete([{"role": "user", "content": prompt}])
        return resp.content.strip()
    except Exception:
        return context
