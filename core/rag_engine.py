"""
RAG Engine — core vector search and document loading
"""
import math
import os
import re
import shutil
from pathlib import Path
from typing import List, Optional


def _cosine(a: list, b: list) -> float:
    """Pure-Python cosine similarity for embedding vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)

from dotenv import load_dotenv
load_dotenv()

from langchain_core.messages import HumanMessage
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import RunnableLambda
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    PyPDFLoader,
    Docx2txtLoader,
    CSVLoader,
    TextLoader,
)
from langchain_core.documents import Document
from langchain_core.runnables import RunnablePassthrough, RunnableParallel
from langchain_core.output_parsers import StrOutputParser

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.parent / "data"
INBOX_DIR  = BASE_DIR / "inbox"
DONE_DIR   = BASE_DIR / "processed"
DB_DIR     = BASE_DIR / "vector_db"
EXPORT_DIR = BASE_DIR / "exports"

for d in [INBOX_DIR, DONE_DIR, DB_DIR, EXPORT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── LLM / Embeddings ───────────────────────────────────────────────────────────
EMBED_MODEL = "nomic-embed-text"   # pull once: ollama pull nomic-embed-text


def get_llm():
    """Return LLM instance based on LLM_PROVIDER env var (ollama or anthropic)."""
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        return ChatAnthropic(model=model, temperature=0.1)
    else:
        from langchain_ollama import ChatOllama
        model = os.getenv("OLLAMA_MODEL", "gemma3")
        num_ctx = int(os.getenv("OLLAMA_NUM_CTX", 8192))
        return ChatOllama(model=model, temperature=0.1, num_ctx=num_ctx)


class _LazyEmbeddings:
    """Loads the embedding model only on first actual use, not at import time."""
    def __init__(self):
        self._model = None

    def _load(self):
        if self._model is None:
            import warnings, logging, sys
            os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
            os.environ["TQDM_DISABLE"] = "1"
            warnings.filterwarnings("ignore")
            for logger_name in (
                "sentence_transformers", "huggingface_hub", "transformers",
                "transformers.modeling_utils", "huggingface_hub.file_download",
            ):
                logging.getLogger(logger_name).setLevel(logging.ERROR)
            _old_stderr = sys.stderr
            try:
                sys.stderr = open(os.devnull, "w")
                from langchain_huggingface import HuggingFaceEmbeddings
                self._model = HuggingFaceEmbeddings(
                    model_name="all-MiniLM-L6-v2",
                    model_kwargs={"device": "cpu"},
                )
            finally:
                sys.stderr.close()
                sys.stderr = _old_stderr
                os.environ.pop("TQDM_DISABLE", None)
        return self._model

    def embed_documents(self, texts):
        return self._load().embed_documents(texts)

    def embed_query(self, text):
        return self._load().embed_query(text)


llm = get_llm()
embeddings = _LazyEmbeddings()


def unload_llm():
    """Ask Ollama to immediately evict the model from VRAM/RAM (keep_alive=0).
    No-op when using any other provider."""
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    if provider != "ollama":
        return
    try:
        import requests
        model = os.getenv("OLLAMA_MODEL", "gemma3")
        requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "keep_alive": 0},
            timeout=5,
        )
    except Exception:
        pass

# ── Vector DB ──────────────────────────────────────────────────────────────────
vectorstore = Chroma(
    persist_directory=str(DB_DIR),
    embedding_function=embeddings,
    collection_name="parallax",
)

splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)

retriever = vectorstore.as_retriever(search_kwargs={"k": 5})


def _format_docs(docs: List[Document]) -> str:
    parts = []
    for d in docs:
        src = d.metadata.get("source_file", "")
        header = f"[Source: {src}]\n" if src else ""
        parts.append(header + d.page_content)
    return "\n\n---\n\n".join(parts)


# ── Analytical keywords & k resolver ──────────────────────────────────────────

_ANALYTICAL_KEYWORDS = {
    "compare", "comparison", "vs", "versus", "difference", "between",
    "summarize", "summary", "overview", "report", "analyze", "analysis",
    "trend", "trends", "findings", "insights", "key points", "list all",
    "what are all", "across", "all available", "full list",
}


def _resolve_k(question: str) -> int:
    """Return retriever k appropriate for this question type."""
    q_lower = question.lower()
    if any(kw in q_lower for kw in _ANALYTICAL_KEYWORDS):
        return 15
    return 8


def _infer_mode(question: str) -> str:
    """Classify question into prompt mode: 'analytical' or 'general'."""
    q_lower = question.lower()
    if any(kw in q_lower for kw in _ANALYTICAL_KEYWORDS):
        return "analytical"
    return "general"


# ── Prompt templates ───────────────────────────────────────────────────────────

_PROMPT_SYSTEM = {
    "general": (
        "You are Parallax, an AI research assistant with access to indexed documents.\n"
        "Answer using ONLY the provided context. If the information is not present, say so clearly.\n\n"
        "FORMATTING RULES (always follow):\n"
        "- Use **bold** for key terms, names, numbers, and important facts\n"
        "- Use bullet points (- item) for lists of 3+ items\n"
        "- Use ## Section heading when the answer has multiple distinct parts\n"
        "- Use `inline code` for tech stack names, tools, frameworks\n"
        "- Keep paragraphs short (2-3 sentences max)\n"
        "- Do NOT output raw unformatted prose"
    ),
    "analytical": (
        "You are Parallax, an AI research analyst. Synthesize information from the provided "
        "context into a structured, actionable analysis.\n"
        "Use ONLY the provided context. Do not invent data.\n\n"
        "REQUIRED STRUCTURE:\n"
        "## Summary\n"
        "2-3 sentence overview\n\n"
        "## Key Findings\n"
        "- bullet list of facts with **bold** highlights\n\n"
        "## Implications\n"
        "- actionable takeaways (if applicable)\n\n"
        "## Sources\n"
        "- which document each finding comes from\n\n"
        "FORMATTING RULES:\n"
        "- Use **bold** for numbers, metrics, and key terms\n"
        "- Use `code` for tech stack, tools, frameworks\n"
        "- Compare sources explicitly if multiple are present"
    ),
    "file_focused": (
        "You are Parallax, an AI research assistant analyzing a specific document.\n"
        "Use ONLY the provided document content to answer.\n"
        "Be thorough — extract all relevant data points, numbers, and facts.\n\n"
        "FORMATTING RULES (always follow):\n"
        "- Use ## Section headings to organize the answer\n"
        "- Use **bold** for all numbers, salaries, percentages, company names\n"
        "- Use bullet points (- item) for lists\n"
        "- Use `inline code` for tech stack, tools, languages\n"
        "- Do NOT output raw unformatted prose"
    ),
}


# ── Dynamic prompt builder (reads lang + history at call time) ─────────────────

def _build_messages(inputs: dict) -> list:
    """Build LLM input with current lang setting, mode, and optional conversation history."""
    from core.config import get_lang
    lang     = get_lang()
    history  = inputs.get("history") or []
    context  = inputs.get("context", "")
    question = inputs.get("question", "")
    mode     = inputs.get("mode", "general")

    history_str = ""
    if history:
        turns = []
        for u, a in history[-3:]:
            turns.append(f"User: {u}\nAssistant: {a}")
        history_str = "Previous conversation:\n" + "\n\n".join(turns) + "\n\n"

    system_instruction = _PROMPT_SYSTEM.get(mode, _PROMPT_SYSTEM["general"])

    content = (
        f"{system_instruction}\n"
        f"Respond in {lang}.\n\n"
        f"{history_str}"
        f"Context:\n{context}\n\n"
        f"Question: {question}\n\n"
        f"Answer:"
    )
    return [HumanMessage(content=content)]


# ── Token tracking callback for LCEL chains ────────────────────────────────────

class _TokenCallback(BaseCallbackHandler):
    """Tracks Anthropic token usage inside LCEL chain invocations."""

    def __init__(self, operation: str = "rag_query"):
        self.operation = operation

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
                        tin  = um.get("input_tokens", 0)
                        tout = um.get("output_tokens", 0)
                        if tin or tout:
                            track(tin, tout, self.operation)
                            return   # count once per invocation
        except Exception:
            pass


# ── QA chain ───────────────────────────────────────────────────────────────────
# Uses RunnableLambda so prompt is built dynamically (reads lang/history at call time).
qa_chain = RunnableParallel(
    answer=(
        RunnablePassthrough.assign(context=lambda x: _format_docs(retriever.invoke(x["question"])))
        | RunnableLambda(_build_messages)
        | llm
        | StrOutputParser()
    ),
    source_documents=lambda x: retriever.invoke(x["question"]),
)


# ── Loaders ────────────────────────────────────────────────────────────────────
LOADERS = {
    ".pdf":  PyPDFLoader,
    ".docx": Docx2txtLoader,
    ".csv":  CSVLoader,
    ".txt":  TextLoader,
    ".md":   TextLoader,
}

def load_file(path: Path) -> List[Document]:
    suffix = path.suffix.lower()
    loader_cls = LOADERS.get(suffix)
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


# ── Index ──────────────────────────────────────────────────────────────────────
def index_file(path: Path) -> int:
    """Load, chunk, embed and store a single file. Returns chunk count."""
    docs = load_file(path)
    if not docs:
        return 0
    chunks = splitter.split_documents(docs)
    vectorstore.add_documents(chunks)
    return len(chunks)


def index_inbox() -> List[str]:
    """Scan inbox, index every supported file, move to processed/."""
    results = []
    for f in INBOX_DIR.iterdir():
        if f.suffix.lower() not in LOADERS:
            continue
        n = index_file(f)
        if n:
            dest = DONE_DIR / f.name
            shutil.move(str(f), str(dest))
            results.append(f"✅ {f.name} — {n} chunks")
        else:
            results.append(f"⚠️  {f.name} — skipped (unsupported or empty)")
    return results or ["📭 Inbox empty"]


# ── Query ──────────────────────────────────────────────────────────────────────

def _known_files() -> List[str]:
    """Return list of unique source_file values currently in the vectorstore."""
    try:
        col = vectorstore._collection
        if not col.count():
            return []
        data = col.get(include=["metadatas"])
        return list({m["source_file"] for m in data["metadatas"] if m.get("source_file")})
    except Exception:
        return []


_FILE_SIM_THRESHOLD = float(os.getenv("RAG_FILE_SIM_THRESHOLD", "0.55"))


def _detect_file_in_question(question: str, extra_history: Optional[List[str]] = None) -> Optional[str]:
    """
    Return the most relevant indexed filename for this question.

    Strategy (ordered by confidence):
    1. Exact substring match — filename or stem appears literally in the query.
    2. Keyword overlap — any significant word from the filename stem appears in the query.
    3. Semantic similarity — cosine sim between query embedding and filename embedding.
    4. History fallback — repeat strategies 1-2 on recent conversation turns.

    For intel: sources (intel:reddit, intel:hackernews etc.) we do NOT auto-select
    them by filename similarity — they should only match via explicit mention or
    when the entire query is clearly about that specific source.
    """
    known = _known_files()
    if not known:
        return None

    q_lower = question.lower()
    q_words = set(re.findall(r'\b\w{4,}\b', q_lower))  # meaningful words (4+ chars)

    # Separate user files from intel: sources
    user_files = [f for f in known if not f.startswith("intel:")]
    intel_files = [f for f in known if f.startswith("intel:")]

    # --- Strategy 1: exact substring match (user files first, then intel) ---
    for fname in user_files + intel_files:
        stem = re.sub(r'\.[^.]+$', '', fname).lower()
        if fname.lower() in q_lower or stem in q_lower:
            return fname

    # --- Strategy 2: keyword overlap for user files ---
    best_overlap = (0, None)
    for fname in user_files:
        stem = re.sub(r'[_\-.]', ' ', re.sub(r'\.[^.]+$', '', fname)).lower()
        stem_words = set(re.findall(r'\b\w{4,}\b', stem))
        overlap = len(q_words & stem_words)
        if overlap > best_overlap[0]:
            best_overlap = (overlap, fname)

    if best_overlap[0] >= 2:  # at least 2 meaningful words match
        return best_overlap[1]

    # --- Strategy 3: semantic similarity (user files only, skip intel) ---
    if user_files:
        try:
            q_vec = embeddings.embed_query(question)
            candidates = []
            for fname in user_files:
                stem_text = re.sub(r'[_\-.]', ' ', re.sub(r'\.[^.]+$', '', fname))
                f_vec = embeddings.embed_query(stem_text)
                sim = _cosine(q_vec, f_vec)
                candidates.append((sim, fname))
            candidates.sort(reverse=True)
            if candidates and candidates[0][0] >= _FILE_SIM_THRESHOLD:
                return candidates[0][1]
        except Exception:
            pass

    # --- Strategy 4: history fallback (substring + keyword) ---
    if extra_history:
        for text in reversed(extra_history):
            t_lower = text.lower()
            t_words = set(re.findall(r'\b\w{4,}\b', t_lower))
            for fname in user_files:
                stem = re.sub(r'\.[^.]+$', '', fname).lower()
                if fname.lower() in t_lower or stem in t_lower:
                    return fname
            for fname in user_files:
                stem = re.sub(r'[_\-.]', ' ', re.sub(r'\.[^.]+$', '', fname)).lower()
                stem_words = set(re.findall(r'\b\w{4,}\b', stem))
                if len(t_words & stem_words) >= 2:
                    return fname

    return None


def _ask_file(question: str, source_file: str, history: Optional[List] = None) -> dict:
    """Fetch all chunks for source_file and query LLM with lang + history."""
    col = vectorstore._collection
    data = col.get(where={"source_file": source_file}, include=["documents"])
    chunks = data.get("documents") or []
    if not chunks:
        return {"answer": f"File «{source_file}» not found in knowledge base.", "sources": []}

    # Adaptive chunk cap: analytical questions get more context
    max_chunks = max(_resolve_k(question) * 2, 20)
    context = f"[Source: {source_file}]\n\n" + "\n\n---\n\n".join(chunks[:max_chunks])

    messages = _build_messages({
        "context": context,
        "question": question,
        "history": history,
        "mode": "file_focused",
    })
    response = llm.invoke(messages)

    from core.token_tracker import track_response
    track_response(response, "rag_file_query")

    return {"answer": response.content, "sources": [source_file]}


def _similarity_search_scoped(question: str, k: int, scope: str) -> list:
    """
    Run similarity_search with scope filtering via ChromaDB $in filter.

      all   → balanced merge: general search + guaranteed doc coverage.
              User docs are often outnumbered by intel chunks, so a pure
              semantic search on 'all' tends to return only intel results.
              We fix this by always including top doc-file results alongside
              general results, letting the LLM pick what's relevant.
      docs  → only locally uploaded files
      intel → only collected research (HN, Reddit, GitHub, RSS...)
    """
    known = _known_files()
    doc_files   = [f for f in known if not f.startswith("intel:")]
    intel_files = [f for f in known if f.startswith("intel:")]

    if scope == "docs":
        if not doc_files:
            return []
        return vectorstore.similarity_search(question, k=k, filter={"source_file": {"$in": doc_files}})

    if scope == "intel":
        if not intel_files:
            return []
        return vectorstore.similarity_search(question, k=k, filter={"source_file": {"$in": intel_files}})

    # scope == "all": balanced merge
    general = vectorstore.similarity_search(question, k=k)

    if not doc_files:
        return general

    # Always pull some results from user docs to prevent intel-volume bias.
    # Cross-lingual queries (e.g. Russian question about English-named file) won't
    # rank doc chunks highly in a pure semantic search across the full corpus.
    k_docs = max(2, k // 3)
    doc_results = vectorstore.similarity_search(
        question, k=k_docs, filter={"source_file": {"$in": doc_files}}
    )

    # Merge: general first (already ranked by relevance), append doc chunks not present
    seen = {d.page_content[:100] for d in general}
    extra = [d for d in doc_results if d.page_content[:100] not in seen]
    return general + extra


def ask(
    question: str,
    source_file: Optional[str] = None,
    history: Optional[List] = None,
    scope: Optional[str] = None,
) -> dict:
    """
    Run RAG query. Returns {answer, sources}.

    Args:
        question:    user question
        source_file: force search within this specific indexed file
        history:     conversation context — list of (user_msg, assistant_msg) tuples
        scope:       search scope — "all" | "docs" | "intel"
                     If None, reads current value from config (set via /set mod)
    """
    if scope is None:
        from core.config import get_mod
        scope = get_mod()

    # In docs mode, file auto-detection is always on (we're looking in documents)
    # In intel mode, skip file detection (intel sources aren't files)
    history_texts = [u for u, a in (history or [])]

    if source_file is None and scope != "intel":
        source_file = _detect_file_in_question(question, extra_history=history_texts)

    if source_file:
        try:
            return _ask_file(question, source_file, history=history)
        except Exception as e:
            print(f"[RAG] File query failed for {source_file}: {e}")

    # Adaptive retrieval with scope filtering
    k = _resolve_k(question)
    docs = _similarity_search_scoped(question, k=k, scope=scope)

    if not docs:
        scope_label = {"docs": "local documents", "intel": "research intel", "all": "knowledge base"}
        return {
            "answer": f"No relevant information found in {scope_label.get(scope, 'knowledge base')}.",
            "sources": [],
        }

    context = _format_docs(docs)
    mode = _infer_mode(question)
    messages = _build_messages({
        "context": context,
        "question": question,
        "history": history or [],
        "mode": mode,
    })
    response = llm.invoke(
        messages,
        config={"callbacks": [_TokenCallback("rag_query")]},
    )
    from core.token_tracker import track_response
    track_response(response, "rag_query")
    sources = list({doc.metadata.get("source_file", "unknown") for doc in docs})
    return {"answer": response.content, "sources": sources}


def delete_file(source_file: str) -> int:
    """Remove all chunks belonging to source_file. Returns number of deleted chunks."""
    col = vectorstore._collection
    data = col.get(where={"source_file": source_file}, include=["metadatas"])
    ids = data.get("ids", [])
    if ids:
        col.delete(ids=ids)
    return len(ids)


def stats() -> dict:
    col = vectorstore._collection
    count = col.count()
    files = set()
    if count:
        data = col.get(include=["metadatas"])
        for m in data["metadatas"]:
            if m.get("source_file"):
                files.add(m["source_file"])
    return {"chunks": count, "files": len(files), "file_list": sorted(files)}
