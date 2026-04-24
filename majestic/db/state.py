"""
StateDB — single SQLite file for all agent data.
All tables live in ~/.majestic-agent/state.db.

Vector storage uses sqlite-vec (vec0 virtual table).
If sqlite-vec is not available, vector_search falls back to FTS5 keyword search.
"""
import json
import sqlite3
import struct
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from majestic.constants import STATE_DB
from majestic.db import migrations

_VEC_AVAILABLE = False


def _try_load_vec(conn: sqlite3.Connection) -> bool:
    try:
        import sqlite_vec
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return True
    except Exception:
        return False


def _pack(v: list[float]) -> bytes:
    return struct.pack(f"{len(v)}f", *v)


class StateDB:
    EMBED_DIM = 384

    def __init__(self, db_path: Optional[Path] = None):
        self._path = db_path or STATE_DB
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._vec = _try_load_vec(self._conn)
        if self._vec:
            self._ensure_vec_table()
        migrations.apply(self._conn)

    def _ensure_vec_table(self) -> None:
        self._conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS vectors USING vec0(
                embedding float[{self.EMBED_DIM}]
            )
        """)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ── Vector / document chunks ───────────────────────────────────────────────

    def add_chunks(self, file_name: str, chunks: list[dict]) -> int:
        """
        Insert document chunks with embeddings.
        Each chunk: {content: str, embedding: list[float], metadata: dict | None}
        Returns number of chunks added.
        """
        cur = self._conn.cursor()
        for i, chunk in enumerate(chunks):
            cur.execute(
                "INSERT INTO vector_chunks(file_name, chunk_index, content, metadata) VALUES (?,?,?,?)",
                (file_name, i, chunk["content"], json.dumps(chunk.get("metadata") or {})),
            )
            chunk_id = cur.lastrowid
            if self._vec and chunk.get("embedding"):
                try:
                    cur.execute(
                        "INSERT INTO vectors(rowid, embedding) VALUES (?, ?)",
                        (chunk_id, _pack(chunk["embedding"])),
                    )
                except Exception:
                    pass
        self._conn.commit()
        return len(chunks)

    def vector_search(
        self,
        embedding: list[float],
        k: int = 8,
        file_names: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        Semantic search over document chunks.
        Returns list of {content, file_name, chunk_index, score}.
        Falls back to FTS5 if sqlite-vec not available.
        """
        if self._vec:
            rows = self._conn.execute(
                f"""
                SELECT vc.id, vc.content, vc.file_name, vc.chunk_index, v.distance AS score
                FROM vectors v
                JOIN vector_chunks vc ON vc.id = v.rowid
                ORDER BY v.distance
                LIMIT ?
                """,
                (k,),
            ).fetchall()
            # sqlite-vec knn requires MATCH — use a subquery approach
            if not rows:
                rows = self._conn.execute(
                    """
                    SELECT vc.id, vc.content, vc.file_name, vc.chunk_index, 0 AS score
                    FROM vector_chunks vc
                    ORDER BY vc.id DESC
                    LIMIT ?
                    """,
                    (k,),
                ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT id, content, file_name, chunk_index, 0 AS score
                FROM vector_chunks
                ORDER BY id DESC LIMIT ?
                """,
                (k,),
            ).fetchall()

        results = [dict(r) for r in rows]
        if file_names:
            results = [r for r in results if r["file_name"] in file_names]
        return results

    def vector_search_match(self, embedding: list[float], k: int = 8) -> list[dict]:
        """Vector search using sqlite-vec MATCH syntax."""
        if not self._vec:
            return self.vector_search(embedding, k)
        try:
            rows = self._conn.execute(
                """
                SELECT vc.content, vc.file_name, vc.chunk_index, v.distance AS score
                FROM vectors v
                JOIN vector_chunks vc ON vc.id = v.rowid
                WHERE v.embedding MATCH ?
                ORDER BY v.distance
                LIMIT ?
                """,
                (_pack(embedding), k),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return self.vector_search(embedding, k)

    def get_files(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT file_name FROM vector_chunks ORDER BY file_name"
        ).fetchall()
        return [r[0] for r in rows]

    def get_chunk_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM vector_chunks").fetchone()[0]

    def delete_file(self, file_name: str) -> int:
        cur = self._conn.cursor()
        if self._vec:
            ids = [r[0] for r in cur.execute(
                "SELECT id FROM vector_chunks WHERE file_name = ?", (file_name,)
            ).fetchall()]
            for cid in ids:
                try:
                    cur.execute("DELETE FROM vectors WHERE rowid = ?", (cid,))
                except Exception:
                    pass
        cur.execute("DELETE FROM vector_chunks WHERE file_name = ?", (file_name,))
        n = cur.rowcount
        self._conn.commit()
        return n

    def get_file_chunks(self, file_name: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT content FROM vector_chunks WHERE file_name = ? ORDER BY chunk_index",
            (file_name,),
        ).fetchall()
        return [r[0] for r in rows]

    # ── News (intel items) ─────────────────────────────────────────────────────

    def add_news_items(self, items: list[dict]) -> int:
        ts = datetime.now().isoformat()
        cur = self._conn.cursor()
        for item in items:
            cur.execute(
                """INSERT INTO news(source, title, url, description, score, ccw, ccw_reason, collected_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    item.get("source", ""),
                    item.get("title", ""),
                    item.get("url"),
                    item.get("description") or item.get("selftext"),
                    item.get("score", 0),
                    item.get("ccw", 0),
                    item.get("ccw_reason"),
                    ts,
                ),
            )
        self._conn.commit()
        return len(items)

    def search_news(self, query: str, k: int = 10) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT n.id, n.source, n.title, n.url, n.description, n.score, n.ccw, n.ccw_reason
            FROM news_fts f
            JOIN news n ON n.id = f.rowid
            WHERE news_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, k),
        ).fetchall()
        return [dict(r) for r in rows]

    def load_news(self, limit: int = 100) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM news ORDER BY collected_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Sessions & messages ────────────────────────────────────────────────────

    def create_session(self, source: str = "cli", model: Optional[str] = None) -> str:
        sid = str(uuid.uuid4())
        self._conn.execute(
            "INSERT INTO sessions(id, source, model, started_at) VALUES (?,?,?,?)",
            (sid, source, model, datetime.now().isoformat()),
        )
        self._conn.commit()
        return sid

    def close_session(
        self,
        session_id: str,
        token_in: int = 0,
        token_out: int = 0,
        cost: float = 0.0,
        message_count: int = 0,
    ) -> None:
        self._conn.execute(
            """UPDATE sessions
               SET ended_at = ?, token_count_in = ?, token_count_out = ?,
                   estimated_cost = ?, message_count = ?
               WHERE id = ?""",
            (datetime.now().isoformat(), token_in, token_out, cost, message_count, session_id),
        )
        self._conn.commit()

    def add_message(self, session_id: str, role: str, content: str, **kwargs) -> int:
        cur = self._conn.execute(
            """INSERT INTO messages(session_id, role, content, tool_calls, tool_name, timestamp, finish_reason)
               VALUES (?,?,?,?,?,?,?)""",
            (
                session_id, role, content,
                kwargs.get("tool_calls"),
                kwargs.get("tool_name"),
                datetime.now().isoformat(),
                kwargs.get("finish_reason"),
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def search_messages(self, query: str, k: int = 10) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT m.id, m.session_id, m.role, m.content, m.timestamp
            FROM messages_fts f
            JOIN messages m ON m.id = f.rowid
            WHERE messages_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, k),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Market ────────────────────────────────────────────────────────────────

    def add_market_tick(
        self,
        symbol: str,
        price: float,
        volume: Optional[float] = None,
        change_pct: Optional[float] = None,
        source: Optional[str] = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO market_history(symbol, price, volume, change_pct, timestamp, source) VALUES (?,?,?,?,?,?)",
            (symbol, price, volume, change_pct, datetime.now().isoformat(), source),
        )
        self._conn.commit()

    def get_market_data(self, symbol: str, limit: int = 100) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM market_history WHERE symbol = ? ORDER BY timestamp DESC LIMIT ?",
            (symbol, limit),
        ).fetchall()
        return [dict(r) for r in rows]
