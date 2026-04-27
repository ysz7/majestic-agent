"""
Schema versioning + migrations for state.db.
Each migration is a list of SQL statements keyed by target version.
apply(conn) brings the DB up to SCHEMA_VERSION from whatever it currently is.
"""

SCHEMA_VERSION = 2

# ── Version 1 — initial schema ─────────────────────────────────────────────────
_V1 = [
    "PRAGMA journal_mode=WAL",
    "PRAGMA foreign_keys=ON",

    """CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER NOT NULL
    )""",

    # ── Sessions ──────────────────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS sessions (
        id                TEXT PRIMARY KEY,
        source            TEXT NOT NULL DEFAULT 'cli',
        user_id           TEXT,
        model             TEXT,
        started_at        TEXT NOT NULL,
        ended_at          TEXT,
        message_count     INTEGER NOT NULL DEFAULT 0,
        token_count_in    INTEGER NOT NULL DEFAULT 0,
        token_count_out   INTEGER NOT NULL DEFAULT 0,
        estimated_cost    REAL    NOT NULL DEFAULT 0.0,
        parent_session_id TEXT    REFERENCES sessions(id),
        title             TEXT
    )""",

    # ── Messages ──────────────────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS messages (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id    TEXT    NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        role          TEXT    NOT NULL,
        content       TEXT    NOT NULL,
        tool_calls    TEXT,
        tool_name     TEXT,
        timestamp     TEXT    NOT NULL,
        finish_reason TEXT
    )""",

    """CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
        content,
        content='messages',
        content_rowid='id'
    )""",

    """CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
        INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
    END""",

    """CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
        INSERT INTO messages_fts(messages_fts, rowid, content)
        VALUES ('delete', old.id, old.content);
    END""",

    # ── News (intel items) ────────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS news (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        source       TEXT    NOT NULL,
        title        TEXT    NOT NULL,
        url          TEXT,
        description  TEXT,
        score        INTEGER DEFAULT 0,
        ccw          INTEGER DEFAULT 0,
        ccw_reason   TEXT,
        collected_at TEXT    NOT NULL
    )""",

    """CREATE VIRTUAL TABLE IF NOT EXISTS news_fts USING fts5(
        title,
        description,
        content='news',
        content_rowid='id'
    )""",

    """CREATE TRIGGER IF NOT EXISTS news_ai AFTER INSERT ON news BEGIN
        INSERT INTO news_fts(rowid, title, description)
        VALUES (new.id, new.title, COALESCE(new.description, ''));
    END""",

    # ── Reports ───────────────────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS reports (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        title      TEXT    NOT NULL,
        content    TEXT    NOT NULL,
        created_at TEXT    NOT NULL,
        file_name  TEXT
    )""",

    """CREATE VIRTUAL TABLE IF NOT EXISTS reports_fts USING fts5(
        title,
        content,
        content='reports',
        content_rowid='id'
    )""",

    """CREATE TRIGGER IF NOT EXISTS reports_ai AFTER INSERT ON reports BEGIN
        INSERT INTO reports_fts(rowid, title, content)
        VALUES (new.id, new.title, new.content);
    END""",

    # ── Market history ────────────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS market_history (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol     TEXT    NOT NULL,
        price      REAL,
        volume     REAL,
        change_pct REAL,
        timestamp  TEXT    NOT NULL,
        source     TEXT
    )""",

    "CREATE INDEX IF NOT EXISTS idx_market ON market_history(symbol, timestamp)",

    # ── Schedules ─────────────────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS schedules (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT    NOT NULL,
        cron_expr       TEXT    NOT NULL,
        prompt          TEXT    NOT NULL,
        delivery_target TEXT,
        last_run        TEXT,
        next_run        TEXT,
        enabled         INTEGER NOT NULL DEFAULT 1
    )""",

    # ── Document chunks (metadata) ────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS vector_chunks (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        file_name   TEXT    NOT NULL,
        chunk_index INTEGER NOT NULL,
        content     TEXT    NOT NULL,
        metadata    TEXT
    )""",

    "CREATE INDEX IF NOT EXISTS idx_chunks_file ON vector_chunks(file_name)",
]

# ── Version 2 — parallel schedules ────────────────────────────────────────────
_V2 = [
    "ALTER TABLE schedules ADD COLUMN parallel INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE schedules ADD COLUMN subtasks  TEXT",
]

# Map version → statements that bring DB TO that version
_MIGRATIONS: dict[int, list[str]] = {
    1: _V1,
    2: _V2,
}


def _current_version(conn) -> int:
    try:
        row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        return row[0] if row else 0
    except Exception:
        return 0


def apply(conn) -> None:
    """Apply all pending migrations in order."""
    current = _current_version(conn)
    for version in sorted(_MIGRATIONS):
        if version <= current:
            continue
        for sql in _MIGRATIONS[version]:
            conn.execute(sql)
        # Upsert schema version
        if current == 0:
            conn.execute("INSERT INTO schema_version(version) VALUES (?)", (version,))
        else:
            conn.execute("UPDATE schema_version SET version = ?", (version,))
        conn.commit()
        current = version
