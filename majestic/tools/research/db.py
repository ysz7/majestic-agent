"""
SQLite store for accumulated research articles.

Deduplicates by URL hash so repeated /research runs only add new items.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import date, timedelta
from pathlib import Path


def _url_hash(url: str, title: str) -> str:
    key = url.strip().lower() if url.strip() else title.strip().lower()[:120]
    return hashlib.sha256(key.encode()).hexdigest()


class ResearchDB:
    def __init__(self, db_path: str) -> None:
        self._path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_schema()

    def _create_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS articles (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                url_hash   TEXT    UNIQUE NOT NULL,
                url        TEXT,
                title      TEXT    NOT NULL,
                summary    TEXT,
                source     TEXT,
                category   TEXT,
                date       TEXT,
                fetched_at TEXT    DEFAULT (date('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_art_date     ON articles(date DESC);
            CREATE INDEX IF NOT EXISTS idx_art_category ON articles(category);
            CREATE INDEX IF NOT EXISTS idx_art_fetched  ON articles(fetched_at DESC);
        """)
        self._conn.commit()

    # ── Write ─────────────────────────────────────────────────────────────────

    def insert_articles(self, articles: list[dict]) -> tuple[int, int]:
        """Insert new articles, skip duplicates.

        Returns (new_count, skipped_count).
        """
        new = skipped = 0
        for a in articles:
            h = _url_hash(a.get("url", ""), a.get("title", ""))
            try:
                self._conn.execute(
                    """INSERT INTO articles
                       (url_hash, url, title, summary, source, category, date)
                       VALUES (?,?,?,?,?,?,?)""",
                    (h, a.get("url"), a.get("title", ""),
                     a.get("summary", ""), a.get("source", ""),
                     a.get("category", ""), a.get("date", "")),
                )
                new += 1
            except sqlite3.IntegrityError:
                skipped += 1
        self._conn.commit()
        return new, skipped

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_articles(self, days: int = 30, category: str = "") -> list[dict]:
        """Return articles fetched in the last *days* days, optionally filtered."""
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        if category:
            cur = self._conn.execute(
                """SELECT title, summary, source, category, date, url
                   FROM articles
                   WHERE fetched_at >= ? AND category = ?
                   ORDER BY date DESC, fetched_at DESC""",
                (cutoff, category),
            )
        else:
            cur = self._conn.execute(
                """SELECT title, summary, source, category, date, url
                   FROM articles
                   WHERE fetched_at >= ?
                   ORDER BY date DESC, fetched_at DESC""",
                (cutoff,),
            )
        cols = ["title", "summary", "source", "category", "date", "url"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def stats(self) -> dict:
        total = self._conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        oldest = self._conn.execute("SELECT MIN(fetched_at) FROM articles").fetchone()[0]
        newest = self._conn.execute("SELECT MAX(fetched_at) FROM articles").fetchone()[0]
        by_cat = self._conn.execute(
            "SELECT category, COUNT(*) FROM articles GROUP BY category ORDER BY 2 DESC"
        ).fetchall()
        return {"total": total, "oldest": oldest, "newest": newest,
                "by_category": dict(by_cat)}

    def close(self) -> None:
        self._conn.close()
