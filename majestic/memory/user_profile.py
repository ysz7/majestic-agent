"""
User profile — persistent store for user preferences and interaction patterns.

Schema
------
profile
    key        TEXT PRIMARY KEY
    value      TEXT NOT NULL
    updated_at TEXT NOT NULL  (ISO-8601, UTC)

Well-known keys (auto-updated by ``update_from_interaction``)
-------------------------------------------------------------
preferred_language   — detected language code, e.g. "en", "uk"
common_topics        — JSON list of the most-seen topic words
interaction_count    — total number of interactions observed
last_seen            — ISO-8601 timestamp of latest interaction
"""

import json
import re
import sqlite3
import threading
from collections import Counter
from datetime import datetime, timezone
from typing import Any


_CREATE_PROFILE = """
CREATE TABLE IF NOT EXISTS profile (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);
"""

# Common English stop-words to exclude from topic extraction
_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "up", "about", "into", "through", "is",
        "are", "was", "were", "be", "been", "being", "have", "has", "had",
        "do", "does", "did", "will", "would", "could", "should", "may",
        "might", "shall", "can", "need", "dare", "used", "ought", "it",
        "i", "you", "he", "she", "we", "they", "me", "him", "her", "us",
        "them", "my", "your", "his", "our", "their", "this", "that", "these",
        "those", "not", "no", "nor", "so", "yet", "both", "either", "neither",
        "each", "few", "more", "most", "other", "some", "such", "what",
        "which", "who", "whom", "how", "when", "where", "why", "all", "any",
    }
)

# Naive language detection by character range
_CYR_RE = re.compile(r"[Ѐ-ӿ]")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _detect_language(text: str) -> str:
    """Return a simple language code based on script heuristics."""
    cyrillic_ratio = len(_CYR_RE.findall(text)) / max(len(text), 1)
    if cyrillic_ratio > 0.2:
        return "uk"  # Ukrainian / Russian Cyrillic
    return "en"


def _extract_topics(text: str, top_n: int = 10) -> list[str]:
    """Extract the most frequent meaningful words from *text*."""
    words = re.findall(r"[a-zA-ZЀ-ӿ]{3,}", text.lower())
    filtered = [w for w in words if w not in _STOP_WORDS]
    return [word for word, _ in Counter(filtered).most_common(top_n)]


class UserProfile:
    """Persistent key/value store for user preferences and behavioural patterns."""

    def __init__(self, db_path: str) -> None:
        """Open (or create) the profile database at *db_path*.

        Args:
            db_path: Filesystem path to the SQLite file.
                     Use ``":memory:"`` for a transient in-process store.
        """
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute(_CREATE_PROFILE)

    # ------------------------------------------------------------------
    # Core key/value API
    # ------------------------------------------------------------------

    def set(self, key: str, value: str) -> None:
        """Upsert a profile entry.

        Args:
            key: Profile key (e.g. ``"preferred_language"``).
            value: String value to store.
        """
        now = _utcnow()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO profile (key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                                               updated_at=excluded.updated_at
                """,
                (key, value, now),
            )
            self._conn.commit()

    def get(self, key: str, default: str = "") -> str:
        """Retrieve the value for *key*, returning *default* if absent.

        Args:
            key: Profile key to look up.
            default: Fallback string.

        Returns:
            Stored string value or *default*.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM profile WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else default

    def get_all(self) -> dict[str, str]:
        """Return all profile entries as a plain dict.

        Returns:
            Mapping of ``{key: value}`` for every stored profile entry.
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT key, value FROM profile"
            ).fetchall()
        return {r["key"]: r["value"] for r in rows}

    def delete(self, key: str) -> None:
        """Remove a profile entry (no-op if absent).

        Args:
            key: Profile key to remove.
        """
        with self._lock:
            self._conn.execute("DELETE FROM profile WHERE key = ?", (key,))
            self._conn.commit()

    # ------------------------------------------------------------------
    # Pattern extraction
    # ------------------------------------------------------------------

    def update_from_interaction(self, task: str, metadata: dict[str, Any]) -> None:
        """Analyse an interaction and update derived profile fields.

        Extracts and stores:
        - ``preferred_language``  — script/language detected in *task*
        - ``common_topics``       — JSON list of frequent meaningful words
        - ``interaction_count``   — running total of observed interactions
        - ``last_seen``           — ISO-8601 timestamp of this call

        Args:
            task: Natural-language task description from the current interaction.
            metadata: Arbitrary metadata dict (currently unused but reserved for
                      future enrichment such as model name, cost, locale hint).
        """
        # Language detection
        detected_lang = _detect_language(task)
        stored_lang = self.get("preferred_language", "")
        # Keep the language that appears more often; only update if new differs
        if not stored_lang or detected_lang != "en":
            self.set("preferred_language", detected_lang)

        # Topic accumulation — merge with previously stored topics
        new_topics = _extract_topics(task)
        stored_raw = self.get("common_topics", "[]")
        try:
            stored_topics: list[str] = json.loads(stored_raw)
        except json.JSONDecodeError:
            stored_topics = []

        # Keep the union, favouring newly seen words at the front, capped at 20
        merged: list[str] = list(dict.fromkeys(new_topics + stored_topics))[:20]
        self.set("common_topics", json.dumps(merged))

        # Interaction counter
        count_str = self.get("interaction_count", "0")
        try:
            count = int(count_str) + 1
        except ValueError:
            count = 1
        self.set("interaction_count", str(count))

        # Last seen timestamp
        self.set("last_seen", _utcnow())

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying database connection."""
        with self._lock:
            self._conn.close()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<UserProfile db={self._db_path!r}>"
