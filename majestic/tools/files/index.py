"""File indexing tool — parse + embed + store into state.db."""
from majestic.tools.registry import tool


@tool(
    name="index_file",
    description=(
        "Index a file or directory into the knowledge base for future searches. "
        "Supports: .pdf, .docx, .md, .txt, .csv. "
        "Use when the user asks to index, add, or ingest a document."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File or directory path to index",
            },
        },
        "required": ["path"],
    },
)
def index_file(path: str) -> str:
    from pathlib import Path
    from majestic.db.parser import load_and_chunk, SUPPORTED_EXTS
    from majestic.db.state import StateDB

    p = Path(path)
    if not p.exists():
        return f"Path not found: {path}"

    if p.is_dir():
        total = 0
        errors: list[str] = []
        for f in p.rglob("*"):
            if f.suffix.lower() in SUPPORTED_EXTS:
                try:
                    chunks = load_and_chunk(f)
                    if chunks:
                        total += StateDB().embed_and_store(f.name, chunks)
                except Exception as e:
                    errors.append(f"{f.name}: {e}")
        msg = f"Indexed directory {path}: {total} chunks"
        if errors:
            msg += f" ({len(errors)} errors: {'; '.join(errors[:3])})"
        return msg

    if p.suffix.lower() not in SUPPORTED_EXTS:
        return f"Unsupported format: {p.suffix}. Supported: {', '.join(SUPPORTED_EXTS)}"

    try:
        chunks = load_and_chunk(p)
        if not chunks:
            return f"No text extracted from {path}"
        n = StateDB().embed_and_store(p.name, chunks)
        return f"Indexed {path}: {n} chunks"
    except Exception as e:
        return f"Error indexing {path}: {e}"
