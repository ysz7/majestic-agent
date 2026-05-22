"""
SQLite store for pain points.

Two tables:
  raw_posts — deduplicated source posts (url_hash as unique key)
  pains     — LLM-extracted pain points linked to source posts
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import date, timedelta
from pathlib import Path


def _url_hash(url: str, title: str) -> str:
    key = url.strip().lower() if url.strip() else title.strip().lower()[:120]
    return hashlib.sha256(key.encode()).hexdigest()


class PainsDB:
    def __init__(self, db_path: str) -> None:
        self._path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_schema()

    def _create_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS raw_posts (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                url_hash   TEXT    UNIQUE NOT NULL,
                url        TEXT,
                title      TEXT    NOT NULL,
                summary    TEXT,
                source     TEXT,
                date       TEXT,
                fetched_at TEXT    DEFAULT (date('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_raw_date    ON raw_posts(date DESC);
            CREATE INDEX IF NOT EXISTS idx_raw_fetched ON raw_posts(fetched_at DESC);

            CREATE TABLE IF NOT EXISTS pains (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                pain_text  TEXT    NOT NULL,
                domain     TEXT,
                source     TEXT,
                url        TEXT,
                date       TEXT,
                fetched_at TEXT    DEFAULT (date('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_pain_date    ON pains(date DESC);
            CREATE INDEX IF NOT EXISTS idx_pain_domain  ON pains(domain);
            CREATE INDEX IF NOT EXISTS idx_pain_fetched ON pains(fetched_at DESC);
        """)
        self._conn.commit()

    # ── Write ─────────────────────────────────────────────────────────────────

    def insert_posts(self, posts: list[dict]) -> tuple[list[dict], int]:
        """Insert new posts, skip duplicates. Returns (new_posts, skipped_count)."""
        new_posts: list[dict] = []
        skipped = 0
        for p in posts:
            h = _url_hash(p.get("url", ""), p.get("title", ""))
            try:
                self._conn.execute(
                    """INSERT INTO raw_posts (url_hash, url, title, summary, source, date)
                       VALUES (?,?,?,?,?,?)""",
                    (h, p.get("url"), p.get("title", ""),
                     p.get("summary", ""), p.get("source", ""),
                     p.get("date", "")),
                )
                new_posts.append(p)
            except sqlite3.IntegrityError:
                skipped += 1
        self._conn.commit()
        return new_posts, skipped

    def insert_pains(self, pains: list[dict]) -> int:
        """Insert extracted pain points. Returns count inserted."""
        count = 0
        for p in pains:
            if not p.get("pain_text"):
                continue
            self._conn.execute(
                """INSERT INTO pains (pain_text, domain, source, url, date)
                   VALUES (?,?,?,?,?)""",
                (p["pain_text"], p.get("domain", "other"),
                 p.get("source", ""), p.get("url", ""),
                 p.get("date", "")),
            )
            count += 1
        self._conn.commit()
        return count

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_pains(self, days: int = 30) -> list[dict]:
        """Return pain points fetched in the last *days* days."""
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        cur = self._conn.execute(
            """SELECT pain_text, domain, source, url, date
               FROM pains
               WHERE fetched_at >= ?
               ORDER BY date DESC, fetched_at DESC""",
            (cutoff,),
        )
        cols = ["pain_text", "domain", "source", "url", "date"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def stats(self) -> dict:
        total_raw   = self._conn.execute("SELECT COUNT(*) FROM raw_posts").fetchone()[0]
        total_pains = self._conn.execute("SELECT COUNT(*) FROM pains").fetchone()[0]
        by_domain   = self._conn.execute(
            "SELECT domain, COUNT(*) FROM pains GROUP BY domain ORDER BY 2 DESC"
        ).fetchall()
        return {
            "total_raw":   total_raw,
            "total_pains": total_pains,
            "by_domain":   dict(by_domain),
        }

    def close(self) -> None:
        self._conn.close()
