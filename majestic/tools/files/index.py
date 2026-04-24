"""File indexing tool — index a file or directory into the knowledge base."""
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
    try:
        from core.rag_engine import index_file as _index, index_directory as _index_dir
    except ImportError as e:
        return f"Indexing unavailable: {e}"

    p = Path(path)
    if not p.exists():
        return f"Path not found: {path}"

    try:
        if p.is_dir():
            n = _index_dir(p)
            return f"Indexed directory {path}: {n} chunks"
        else:
            n = _index(p)
            return f"Indexed {path}: {n} chunks"
    except Exception as e:
        return f"Error indexing {path}: {e}"
