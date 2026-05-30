"""
SQLite store for accumulated research articles.

Deduplicates by URL hash so repeated /research runs only add new items.
Articles are scored at insert time: score = recency × source_quality × category_relevance.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from majestic.storage import Store


_SOURCE_WEIGHTS: dict[str, float] = {
    "reuters": 1.0, "bloomberg": 1.0, "ft": 0.95, "wsj": 0.95,
    "techcrunch": 0.9, "wired": 0.9, "hackernews": 0.9, "hn": 0.9,
    "producthunt": 0.85, "coindesk": 0.8, "theguardian": 0.85,
    "bbc": 0.85, "nytimes": 0.9, "reddit": 0.75,
}

_CATEGORY_WEIGHTS: dict[str, float] = {
    "breaking": 1.0, "ai": 0.95, "tech": 0.9, "launches": 0.9,
    "finance": 0.85, "business": 0.8, "macro": 0.8,
    "science": 0.75, "policy": 0.75, "world": 0.7, "general": 0.6,
}


def _url_hash(url: str, title: str) -> str:
    key = url.strip().lower() if url.strip() else title.strip().lower()[:120]
    return hashlib.sha256(key.encode()).hexdigest()


def _compute_score(article: dict) -> float:
    """Score 0.0–1.0: recency × source_quality × category_relevance."""
    art_date = article.get("date") or article.get("fetched_at") or ""
    try:
        delta = (date.today() - date.fromisoformat(art_date[:10])).days
    except Exception:
        delta = 30

    if delta <= 0:
        recency = 1.0
    elif delta <= 1:
        recency = 0.9
    elif delta <= 7:
        recency = 0.7
    elif delta <= 30:
        recency = 0.5
    else:
        recency = 0.3

    src = (article.get("source") or "").lower().replace(" ", "").replace("-", "")
    source_w = _SOURCE_WEIGHTS.get(src, 0.65)

    cat = (article.get("category") or "general").lower()
    cat_w = _CATEGORY_WEIGHTS.get(cat, 0.65)

    return round(recency * source_w * cat_w, 4)


class ResearchDB(Store):
    def __init__(self, db_path: str) -> None:
        super().__init__(db_path)
        self._path = db_path
        self._create_schema()

    def _create_schema(self) -> None:
        # Base schema — score index is created AFTER migration so existing DBs work too
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
                score      REAL    DEFAULT 0.0,
                fetched_at TEXT    DEFAULT (date('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_art_date     ON articles(date DESC);
            CREATE INDEX IF NOT EXISTS idx_art_category ON articles(category);
            CREATE INDEX IF NOT EXISTS idx_art_fetched  ON articles(fetched_at DESC);

            CREATE TABLE IF NOT EXISTS prices (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol      TEXT    NOT NULL,
                name        TEXT,
                asset_class TEXT,
                price       REAL,
                change_24h  REAL,
                change_7d   REAL,
                market_cap  REAL,
                volume_24h  REAL,
                currency    TEXT    DEFAULT 'USD',
                fetched_at  TEXT    DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_prices_fetched ON prices(fetched_at DESC);
            CREATE INDEX IF NOT EXISTS idx_prices_symbol  ON prices(symbol);
        """)
        self._conn.commit()
        # Migration: add score column to existing DBs that predate this feature.
        # PRAGMA is reliable; catching OperationalError would silently swallow real errors.
        # Must run before creating idx_art_score (which references the column).
        self.add_column_if_missing("articles", "score", "score REAL DEFAULT 0.0")
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_art_score ON articles(score DESC)"
        )
        self._conn.commit()

    # ── Write ─────────────────────────────────────────────────────────────────

    def insert_articles(self, articles: list[dict]) -> tuple[list[dict], int]:
        """Insert new articles, skip duplicates.

        Returns (new_articles, skipped_count) where new_articles is the list
        of articles that were actually inserted (not previously seen).
        """
        new_articles: list[dict] = []
        skipped = 0
        for a in articles:
            h = _url_hash(a.get("url", ""), a.get("title", ""))
            score = _compute_score(a)
            try:
                self._conn.execute(
                    """INSERT INTO articles
                       (url_hash, url, title, summary, source, category, date, score)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (h, a.get("url"), a.get("title", ""),
                     a.get("summary", ""), a.get("source", ""),
                     a.get("category", ""), a.get("date", ""), score),
                )
                new_articles.append(a)
            except sqlite3.IntegrityError:
                skipped += 1
        self._conn.commit()
        return new_articles, skipped

    def insert_prices(self, prices: list[dict]) -> int:
        """Insert a price snapshot batch. Returns count inserted."""
        from datetime import datetime as _dt
        ts = _dt.utcnow().isoformat(timespec="seconds")
        count = 0
        for p in prices:
            if p.get("price") is None:
                continue
            self._conn.execute(
                """INSERT INTO prices
                   (symbol, name, asset_class, price, change_24h, change_7d,
                    market_cap, volume_24h, currency, fetched_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (p.get("symbol", ""), p.get("name", ""),
                 p.get("asset_class", ""),
                 p.get("price"), p.get("change_24h"), p.get("change_7d"),
                 p.get("market_cap"), p.get("volume_24h"),
                 p.get("currency", "USD"), ts),
            )
            count += 1
        self._conn.commit()
        return count

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_latest_prices(self) -> tuple[list[dict], str]:
        """Return the most recent price snapshot batch.

        Returns (prices, fetched_at_str). Empty list if no prices stored.
        """
        row = self._conn.execute(
            "SELECT fetched_at FROM prices ORDER BY fetched_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return [], ""
        latest_ts = row[0]
        # Match all rows from the same minute (trim to 16 chars: "YYYY-MM-DDTHH:MM")
        cutoff = latest_ts[:16]
        rows = self._conn.execute(
            """SELECT symbol, name, asset_class, price, change_24h, change_7d,
                      market_cap, volume_24h, currency, fetched_at
               FROM prices
               WHERE fetched_at >= ?
               ORDER BY
                 CASE asset_class WHEN 'crypto' THEN 0 WHEN 'index' THEN 1
                                  WHEN 'commodity' THEN 2 ELSE 3 END,
                 COALESCE(market_cap, 0) DESC""",
            (cutoff,),
        ).fetchall()
        cols = ["symbol", "name", "asset_class", "price", "change_24h", "change_7d",
                "market_cap", "volume_24h", "currency", "fetched_at"]
        return [dict(zip(cols, r)) for r in rows], latest_ts

    def get_articles(self, days: int = 30, category: str = "") -> list[dict]:
        """Return articles fetched in the last *days* days, sorted by score then date."""
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        if category:
            cur = self._conn.execute(
                """SELECT title, summary, source, category, date, url, score
                   FROM articles
                   WHERE fetched_at >= ? AND category = ?
                   ORDER BY score DESC, date DESC, fetched_at DESC""",
                (cutoff, category),
            )
        else:
            cur = self._conn.execute(
                """SELECT title, summary, source, category, date, url, score
                   FROM articles
                   WHERE fetched_at >= ?
                   ORDER BY score DESC, date DESC, fetched_at DESC""",
                (cutoff,),
            )
        cols = ["title", "summary", "source", "category", "date", "url", "score"]
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
