"""
RAG Engine — document indexing and retrieval backed by StateDB + fastembed.
Replaces ChromaDB with sqlite-vec (via StateDB) and HuggingFace with fastembed.
"""
import os
import re
import shutil
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
load_dotenv()

from langchain_core.messages import HumanMessage
from langchain_core.callbacks import BaseCallbackHandler
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    PyPDFLoader, Docx2txtLoader, CSVLoader, TextLoader,
)
from langchain_core.documents import Document

from majestic.constants import MAJESTIC_HOME

# ── Paths ──────────────────────────────────────────────────────────────────────
INBOX_DIR  = MAJESTIC_HOME / "workspace" / "inbox"
DONE_DIR   = MAJESTIC_HOME / "workspace" / "processed"
EXPORT_DIR = MAJESTIC_HOME / "exports"

for _d in [INBOX_DIR, DONE_DIR, EXPORT_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# ── LLM ────────────────────────────────────────────────────────────────────────
def get_llm():
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        return ChatAnthropic(model=model, temperature=0.1)
    from langchain_ollama import ChatOllama
    model   = os.getenv("OLLAMA_MODEL", "gemma3")
    num_ctx = int(os.getenv("OLLAMA_NUM_CTX", 8192))
    return ChatOllama(model=model, temperature=0.1, num_ctx=num_ctx)


llm = get_llm()


def unload_llm() -> None:
    if os.getenv("LLM_PROVIDER", "ollama").lower() != "ollama":
        return
    try:
        import requests
        requests.post(
            "http://localhost:11434/api/generate",
            json={"model": os.getenv("OLLAMA_MODEL", "gemma3"), "keep_alive": 0},
            timeout=5,
        )
    except Exception:
        pass


# ── Embeddings (fastembed, lazy) ───────────────────────────────────────────────
_embed_model = None


def _get_embedder():
    global _embed_model
    if _embed_model is None:
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        from fastembed import TextEmbedding
        _embed_model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")
    return _embed_model


def embed_text(text: str) -> list[float]:
    model = _get_embedder()
    return list(model.embed([text]))[0].tolist()


# ── StateDB singleton ─────────────────────────────────────────────────────────
_db = None


def _get_db():
    global _db
    if _db is None:
        from majestic.db.state import StateDB
        _db = StateDB()
    return _db


# ── Splitter ───────────────────────────────────────────────────────────────────
_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)


# ── Document loaders ───────────────────────────────────────────────────────────
LOADERS = {
    ".pdf":  PyPDFLoader,
    ".docx": Docx2txtLoader,
    ".csv":  CSVLoader,
    ".txt":  TextLoader,
    ".md":   TextLoader,
}


def load_file(path: Path) -> List[Document]:
    loader_cls = LOADERS.get(path.suffix.lower())
    if not loader_cls:
        return []
    try:
        if loader_cls is TextLoader:
            loader = loader_cls(str(path), encoding="utf-8", autodetect_encoding=True)
        else:
            loader = loader_cls(str(path))
        docs = loader.load()
        for doc in docs:
            doc.metadata["source_file"] = path.name
        return docs
    except Exception as e:
        from core.error_logger import log_error
        log_error("rag_engine.load_file", f"Cannot load {path.name}", str(e))
        return []


# ── Indexing ───────────────────────────────────────────────────────────────────

def _docs_to_chunks(docs: List[Document]) -> list[dict]:
    """Split documents, embed each chunk, return list of {content, embedding, metadata}."""
    raw_chunks = _splitter.split_documents(docs)
    result = []
    embedder = _get_embedder()
    texts = [c.page_content for c in raw_chunks]
    embeddings = list(embedder.embed(texts))
    for chunk, emb in zip(raw_chunks, embeddings):
        result.append({
            "content":   chunk.page_content,
            "embedding": emb.tolist(),
            "metadata":  chunk.metadata,
        })
    return result


def index_file(path: Path) -> int:
    """Load, chunk, embed and store a single file. Returns chunk count."""
    docs = load_file(path)
    if not docs:
        return 0
    chunks = _docs_to_chunks(docs)
    return _get_db().add_chunks(path.name, chunks)


def index_file_with_progress(path: Path, on_progress=None) -> int:
    """Like index_file but calls on_progress(done, total) after each batch."""
    docs = load_file(path)
    if not docs:
        return 0
    raw_chunks = _splitter.split_documents(docs)
    total = len(raw_chunks)
    if not total:
        return 0

    embedder = _get_embedder()
    batch_size = max(1, total // 20)
    chunks_out = []
    done = 0
    for i in range(0, total, batch_size):
        batch = raw_chunks[i : i + batch_size]
        embs  = list(embedder.embed([c.page_content for c in batch]))
        for chunk, emb in zip(batch, embs):
            chunks_out.append({
                "content":   chunk.page_content,
                "embedding": emb.tolist(),
                "metadata":  chunk.metadata,
            })
        done += len(batch)
        if on_progress:
            on_progress(done, total)

    _get_db().add_chunks(path.name, chunks_out)
    return total


def add_intel_docs(docs: List[Document]) -> int:
    """Index intel/news documents into StateDB vectors + news table."""
    db = _get_db()
    # Store as vector chunks for semantic search
    chunks = _docs_to_chunks(docs)
    for doc, chunk in zip(docs, chunks):
        source_file = doc.metadata.get("source_file", "intel:unknown")
        db.add_chunks(source_file, [chunk])

    # Also store raw items in news table for FTS5 search
    news_items = []
    for doc in docs:
        meta = doc.metadata
        src  = meta.get("source_file", "intel:unknown").replace("intel:", "")
        lines = doc.page_content.split("\n")
        title = lines[0].lstrip("[").split("]")[-1].strip() if lines else ""
        desc  = "\n".join(lines[1:5]).strip()
        news_items.append({
            "source":      src,
            "title":       title or doc.page_content[:120],
            "url":         meta.get("url"),
            "description": desc,
        })
    if news_items:
        db.add_news_items(news_items)

    return len(docs)


# ── Prompts ────────────────────────────────────────────────────────────────────
_PROMPT_SYSTEM = {
    "general": (
        "You are Majestic, a universal AI agent with access to indexed documents and research.\n"
        "Answer using ONLY the provided context. If the information is not present, say so.\n\n"
        "- Use **bold** for key terms and numbers\n"
        "- Use bullet points for lists of 3+ items\n"
        "- Use ## headings when the answer has multiple parts\n"
        "- Keep paragraphs short"
    ),
    "analytical": (
        "You are Majestic, an AI research analyst. Synthesize the provided context into a structured analysis.\n"
        "Use ONLY the provided context.\n\n"
        "## Summary\n2-3 sentence overview\n\n"
        "## Key Findings\n- bullet list with **bold** highlights\n\n"
        "## Implications\n- actionable takeaways\n\n"
        "## Sources\n- which document each finding comes from"
    ),
    "file_focused": (
        "You are Majestic, an AI agent analyzing a specific document.\n"
        "Use ONLY the provided document content. Extract all relevant facts, numbers, and data points.\n\n"
        "- Use ## headings\n- Use **bold** for numbers and names\n- Use bullet points for lists"
    ),
}

_ANALYTICAL_KW = {
    "compare", "comparison", "vs", "versus", "difference", "summarize", "summary",
    "overview", "report", "analyze", "analysis", "trend", "trends", "findings",
    "insights", "key points", "list all", "what are all", "across", "all available",
}


def _resolve_k(question: str) -> int:
    return 15 if any(kw in question.lower() for kw in _ANALYTICAL_KW) else 8


def _infer_mode(question: str) -> str:
    return "analytical" if any(kw in question.lower() for kw in _ANALYTICAL_KW) else "general"


def _build_messages(context: str, question: str, history, mode: str) -> list:
    from core.config import get_lang
    lang = get_lang()
    history_str = ""
    if history:
        turns = [f"User: {u}\nAssistant: {a}" for u, a in (history or [])[-3:]]
        history_str = "Previous conversation:\n" + "\n\n".join(turns) + "\n\n"
    content = (
        f"{_PROMPT_SYSTEM.get(mode, _PROMPT_SYSTEM['general'])}\n"
        f"Respond in {lang}.\n\n"
        f"{history_str}"
        f"Context:\n{context}\n\n"
        f"Question: {question}\n\nAnswer:"
    )
    return [HumanMessage(content=content)]


class _TokenCallback(BaseCallbackHandler):
    def __init__(self, op: str = "rag_query"):
        self.op = op

    def on_llm_end(self, response, **kwargs):
        if os.getenv("LLM_PROVIDER", "").lower() != "anthropic":
            return
        try:
            from core.token_tracker import track
            for gen_list in response.generations:
                for gen in gen_list:
                    msg = getattr(gen, "message", None)
                    if msg:
                        um = getattr(msg, "usage_metadata", None) or {}
                        tin, tout = um.get("input_tokens", 0), um.get("output_tokens", 0)
                        if tin or tout:
                            track(tin, tout, self.op)
                            return
        except Exception:
            pass


# ── Query ──────────────────────────────────────────────────────────────────────

def _known_files() -> list[str]:
    try:
        return _get_db().get_files()
    except Exception:
        return []


def _detect_file_in_question(question: str, history_texts: list[str] = None) -> Optional[str]:
    known = _known_files()
    if not known:
        return None
    q_lower  = question.lower()
    q_words  = set(re.findall(r'\b\w{4,}\b', q_lower))
    user_files  = [f for f in known if not f.startswith("intel:")]
    intel_files = [f for f in known if f.startswith("intel:")]

    for fname in user_files + intel_files:
        stem = re.sub(r'\.[^.]+$', '', fname).lower()
        if fname.lower() in q_lower or stem in q_lower:
            return fname

    best = (0, None)
    for fname in user_files:
        stem  = re.sub(r'[_\-.]', ' ', re.sub(r'\.[^.]+$', '', fname)).lower()
        words = set(re.findall(r'\b\w{4,}\b', stem))
        n = len(q_words & words)
        if n > best[0]:
            best = (n, fname)
    if best[0] >= 2:
        return best[1]

    return None


def _chunks_to_context(chunks: list[dict]) -> tuple[str, list[str]]:
    parts, sources = [], set()
    for c in chunks:
        src = c.get("file_name", "")
        sources.add(src)
        header = f"[Source: {src}]\n" if src else ""
        parts.append(header + c["content"])
    return "\n\n---\n\n".join(parts), sorted(sources)


def ask(
    question: str,
    source_file: Optional[str] = None,
    history=None,
    scope: Optional[str] = None,
) -> dict:
    if scope is None:
        from core.config import get_mod
        scope = get_mod()

    db = _get_db()
    history_texts = [u for u, a in (history or [])]

    if source_file is None and scope != "intel":
        source_file = _detect_file_in_question(question, history_texts)

    # ── File-focused query ────────────────────────────────────────────────────
    if source_file:
        if source_file.startswith("intel:"):
            src = source_file.replace("intel:", "")
            rows = db.search_news(question, k=20)
            rows = [r for r in rows if r.get("source") == src] or rows[:10]
            chunks = [{"content": f"[{r['source']}] {r['title']}\n{r.get('description','')}", "file_name": source_file} for r in rows]
        else:
            contents = db.get_file_chunks(source_file)
            k = max(_resolve_k(question) * 2, 20)
            chunks = [{"content": c, "file_name": source_file} for c in contents[:k]]

        if not chunks:
            return {"answer": f"No data found for «{source_file}».", "sources": []}

        context, sources = _chunks_to_context(chunks)
        msgs = _build_messages(context, question, history, "file_focused")
        resp = llm.invoke(msgs, config={"callbacks": [_TokenCallback("rag_file")]})
        from core.token_tracker import track_response
        track_response(resp, "rag_file")
        return {"answer": resp.content, "sources": sources}

    # ── Scope-based retrieval ──────────────────────────────────────────────────
    k = _resolve_k(question)
    chunks: list[dict] = []

    if scope in ("docs", "all"):
        emb    = embed_text(question)
        files  = [f for f in _known_files() if not f.startswith("intel:")] if scope == "docs" else None
        chunks += db.vector_search_match(emb, k=k) if not files else [
            c for c in db.vector_search_match(emb, k=k) if c.get("file_name") in files
        ]

    if scope in ("intel", "all"):
        news_rows = db.search_news(question, k=k)
        for r in news_rows:
            chunks.append({
                "content":   f"[{r['source']}] {r['title']}\n{r.get('description') or ''}",
                "file_name": f"intel:{r['source']}",
            })

    if not chunks:
        label = {"docs": "local documents", "intel": "research intel", "all": "knowledge base"}
        return {"answer": f"No relevant information found in {label.get(scope,'knowledge base')}.", "sources": []}

    context, sources = _chunks_to_context(chunks)
    msgs = _build_messages(context, question, history, _infer_mode(question))
    resp = llm.invoke(msgs, config={"callbacks": [_TokenCallback()]})
    from core.token_tracker import track_response
    track_response(resp, "rag_query")
    return {"answer": resp.content, "sources": sources}


def delete_file(source_file: str) -> int:
    return _get_db().delete_file(source_file)


def stats() -> dict:
    db    = _get_db()
    files = db.get_files()
    return {"chunks": db.get_chunk_count(), "files": len(files), "file_list": sorted(files)}
