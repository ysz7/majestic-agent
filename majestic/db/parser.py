"""
Document text extraction and chunking.

Supported formats: .pdf, .docx, .txt, .md, .csv
Chunk size: 512 words with 64-word overlap.
"""
from __future__ import annotations

from pathlib import Path

_CHUNK_WORDS   = 512
_OVERLAP_WORDS = 64

SUPPORTED_EXTS = {".pdf", ".docx", ".txt", ".md", ".csv"}


def load_and_chunk(path: Path) -> list[str]:
    """Extract text from file, return list of overlapping text chunks."""
    text = _extract(path)
    return _chunk(text)


def _extract(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _pdf(path)
    if ext == ".docx":
        return _docx(path)
    if ext in (".txt", ".md", ".csv"):
        return path.read_text(encoding="utf-8", errors="replace")
    raise ValueError(f"Unsupported format: {ext}")


def _pdf(path: Path) -> str:
    from pypdf import PdfReader
    pages = []
    for page in PdfReader(str(path)).pages:
        text = page.extract_text() or ""
        pages.append(text)
    return "\n\n".join(pages)


def _docx(path: Path) -> str:
    import docx2txt
    return docx2txt.process(str(path)) or ""


def _chunk(text: str) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i : i + _CHUNK_WORDS])
        if len(chunk.strip()) > 20:
            chunks.append(chunk)
        i += _CHUNK_WORDS - _OVERLAP_WORDS
    return chunks
