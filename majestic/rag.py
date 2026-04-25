"""RAG interface — semantic search + LLM answer, wraps StateDB."""
from __future__ import annotations

from typing import Optional


def ask(
    question: str,
    source_file: Optional[str] = None,
    history=None,
    scope: Optional[str] = None,
) -> dict:
    from majestic.config import get
    from majestic.db.state import StateDB
    from majestic.llm import get_provider
    from majestic.token_tracker import track

    if scope is None:
        scope = get("search_mode", "all")

    db     = StateDB()
    chunks: list[dict] = []

    if source_file:
        if source_file.startswith("intel:"):
            src  = source_file.replace("intel:", "")
            rows = db.search_news(question, k=20)
            rows = [r for r in rows if r.get("source") == src] or rows[:10]
            chunks = [{"content": f"[{r['source']}] {r['title']}\n{r.get('description','')}", "file_name": source_file} for r in rows]
        else:
            contents = db.get_file_chunks(source_file)
            chunks   = [{"content": c, "file_name": source_file} for c in contents[:20]]
        if not chunks:
            return {"answer": f"No data found for «{source_file}».", "sources": []}
    else:
        if scope in ("docs", "all"):
            chunks += db.semantic_search(question, k=8)
        if scope in ("intel", "all"):
            for r in db.search_news(question, k=8):
                chunks.append({
                    "content":   f"[{r['source']}] {r['title']}\n{r.get('description') or ''}",
                    "file_name": f"intel:{r['source']}",
                })

    if not chunks:
        label = {"docs": "local documents", "intel": "research intel"}.get(scope, "knowledge base")
        return {"answer": f"No relevant information found in {label}.", "sources": []}

    sources = list({c.get("file_name", "") for c in chunks if c.get("file_name")})
    context = "\n---\n".join(c["content"] for c in chunks[:12])

    hist_ctx = ""
    if history:
        for u, a in list(history)[-3:]:
            hist_ctx += f"User: {u}\nAssistant: {a}\n\n"

    lang   = get("language", "EN")
    prompt = (
        f"Answer based on the context. Respond in {lang}.\n\n"
        f"Context:\n{context[:8000]}\n\n"
        + (f"Previous conversation:\n{hist_ctx}" if hist_ctx else "")
        + f"Question: {question}\n\nAnswer:"
    )

    provider = get_provider()
    resp     = provider.complete([{"role": "user", "content": prompt}])

    try:
        um = resp.usage
        if um:
            track(um.input_tokens or 0, um.output_tokens or 0, "rag_query")
    except Exception:
        pass

    return {"answer": resp.content, "sources": sources}


def index_file(path) -> int:
    from majestic.tools.files.index import index_file as _idx
    result = _idx(str(path))
    try:
        return int(result.split(": ")[1].split(" ")[0])
    except Exception:
        return 0


def stats() -> dict:
    from majestic.db.state import StateDB
    db    = StateDB()
    files = db.get_files()
    return {"chunks": db.get_chunk_count(), "files": len(files), "file_list": sorted(files)}
