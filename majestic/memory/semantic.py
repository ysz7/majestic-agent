import re
import sqlite3, threading, json
from pathlib import Path

from majestic.storage import Store

_FTS5_OPERATORS = frozenset({"and", "or", "not"})


def _fts5_query(text: str) -> str:
    """Build a safe FTS5 MATCH expression from free text.

    Extracts alphanumeric words (3+ chars), skips boolean operators,
    and wraps each term in double quotes so FTS5 treats them as literals.
    """
    words = [
        w for w in re.findall(r"\b[A-Za-z0-9_]{3,}\b", text[:400])
        if w.lower() not in _FTS5_OPERATORS
    ][:8]
    if not words:
        return ""
    return " ".join(f'"{w}"' for w in words)

class SemanticMemory(Store):
    """Vector search using sqlite-vec. Falls back to FTS5 if sqlite-vec unavailable."""

    def __init__(self, db_path: str):
        super().__init__(db_path)
        self.db_path = db_path
        self._lock = threading.Lock()
        self._use_vec = False
        self._init_db()

    def _init_db(self):
        with self._get_conn() as conn:
            # Try to load sqlite-vec
            try:
                import sqlite_vec
                conn.enable_load_extension(True)
                sqlite_vec.load(conn)
                conn.enable_load_extension(False)
                self._use_vec = True
            except Exception:
                pass

            # Always create FTS5 table as fallback
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
                USING fts5(source, content)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT,
                    content TEXT,
                    created_at TEXT
                )
            """)

    def _get_conn(self):
        return self._conn

    def index(self, source: str, content: str, chunk_size: int = 500):
        """Split content into chunks and index them."""
        chunks = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]
        with self._lock:
            with self._get_conn() as conn:
                for chunk in chunks:
                    cur = conn.execute(
                        "INSERT INTO chunks (source, content, created_at) VALUES (?, ?, datetime('now'))",
                        (source, chunk)
                    )
                    conn.execute(
                        "INSERT INTO chunks_fts(rowid, source, content) VALUES (?, ?, ?)",
                        (cur.lastrowid, source, chunk)
                    )

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """Search indexed content using FTS5."""
        fts_query = _fts5_query(query)
        if not fts_query:
            return []
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT c.source, c.content
                FROM chunks_fts f
                JOIN chunks c ON c.id = f.rowid
                WHERE chunks_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (fts_query, limit)).fetchall()
            return [{"source": r[0], "content": r[1]} for r in rows]

    def format_for_prompt(self, results: list[dict]) -> str:
        if not results:
            return ""
        lines = ["Relevant context from knowledge base:"]
        for r in results:
            lines.append(f"[{r['source']}]: {r['content'][:300]}")
        return "\n".join(lines)
