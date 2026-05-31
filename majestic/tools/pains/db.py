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

from majestic.storage import Store
from majestic.tools.pains.taxonomy import normalize_domain

SCHEMA_VERSION = 1


def _url_hash(url: str, title: str) -> str:
    key = url.strip().lower() if url.strip() else title.strip().lower()[:120]
    return hashlib.sha256(key.encode()).hexdigest()


class PainsDB(Store):
    def __init__(self, db_path: str) -> None:
        super().__init__(db_path)
        self._path = db_path
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
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                pain_text          TEXT    NOT NULL,
                domain             TEXT,
                intensity          TEXT    DEFAULT 'MEDIUM',
                willingness_to_pay INTEGER DEFAULT 0,
                source             TEXT,
                url                TEXT,
                date               TEXT,
                fetched_at         TEXT    DEFAULT (date('now')),
                schema_version     INTEGER DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_pain_date    ON pains(date DESC);
            CREATE INDEX IF NOT EXISTS idx_pain_domain  ON pains(domain);
            CREATE INDEX IF NOT EXISTS idx_pain_fetched ON pains(fetched_at DESC);
        """)
        self._conn.commit()

        # Migration for existing DBs missing new columns
        self.add_column_if_missing("pains", "intensity", "intensity TEXT DEFAULT 'MEDIUM'")
        self.add_column_if_missing(
            "pains", "willingness_to_pay", "willingness_to_pay INTEGER DEFAULT 0"
        )
        self.add_column_if_missing(
            "pains", "schema_version", "schema_version INTEGER DEFAULT 1"
        )

        # Intensity index — created after migration guarantees column exists
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_pain_intensity ON pains(intensity)")
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
                """INSERT INTO pains
                   (pain_text, domain, intensity, willingness_to_pay, source, url, date, schema_version)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (p["pain_text"], normalize_domain(p.get("domain")),
                 p.get("intensity", "MEDIUM"),
                 1 if p.get("willingness_to_pay") else 0,
                 p.get("source", ""), p.get("url", ""),
                 p.get("date", ""), SCHEMA_VERSION),
            )
            count += 1
        self._conn.commit()
        return count

    def normalize_existing_domains(self) -> int:
        """One-time backfill: map existing free-text domains onto the canonical
        taxonomy. Returns number of rows changed. Idempotent (re-runs are no-ops)."""
        changed = 0
        for rid, dom in self._conn.execute("SELECT id, domain FROM pains").fetchall():
            norm = normalize_domain(dom)
            if norm != dom:
                self._conn.execute("UPDATE pains SET domain=? WHERE id=?", (norm, rid))
                changed += 1
        self._conn.commit()
        return changed

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_pains(self, days: int = 30) -> list[dict]:
        """Return pain points fetched in the last *days* days, ordered by date."""
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        cur = self._conn.execute(
            """SELECT pain_text, domain, intensity, willingness_to_pay, source, url, date
               FROM pains
               WHERE fetched_at >= ?
               ORDER BY date DESC, fetched_at DESC""",
            (cutoff,),
        )
        cols = ["pain_text", "domain", "intensity", "willingness_to_pay", "source", "url", "date"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def get_trending_domains(self, current_days: int = 7, compare_days: int = 14) -> list[dict]:
        """Compare domain pain counts: last current_days vs the prior window.

        Returns list sorted by abs(delta_pct) descending.
        Only domains with at least 1 pain in the current window are included.
        """
        today = date.today()
        cutoff_now  = (today - timedelta(days=current_days)).isoformat()
        cutoff_prev = (today - timedelta(days=compare_days)).isoformat()

        curr_rows = self._conn.execute(
            "SELECT domain, COUNT(*) FROM pains WHERE fetched_at >= ? GROUP BY domain",
            (cutoff_now,),
        ).fetchall()
        prev_rows = self._conn.execute(
            "SELECT domain, COUNT(*) FROM pains "
            "WHERE fetched_at >= ? AND fetched_at < ? GROUP BY domain",
            (cutoff_prev, cutoff_now),
        ).fetchall()

        curr = {r[0]: r[1] for r in curr_rows}
        prev = {r[0]: r[1] for r in prev_rows}

        trends: list[dict] = []
        for domain, n in curr.items():
            p = prev.get(domain, 0)
            delta_pct = int((n - p) / p * 100) if p > 0 else (100 if n > 0 else 0)
            trends.append({"domain": domain, "current": n, "prev": p, "delta_pct": delta_pct})

        trends.sort(key=lambda x: -abs(x["delta_pct"]))
        return trends

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
