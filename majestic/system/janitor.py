"""
Janitor — periodic cleanup tasks for the Majestic agent framework.

Removes stale temporary files, trims oversized databases and checkpoint
directories, and records the time of the last run so the startup manager
can decide whether to invoke the janitor again.
"""

import json
import logging
import os
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from majestic.storage import connect

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TEMP_MAX_AGE_HOURS: int = 24          # files in temp/ older than this are deleted
_EPISODIC_MAX_ROWS: int = 1_000        # maximum task records kept in episodic DB
_CHECKPOINT_MAX_AGE_DAYS: int = 7      # completed checkpoints older than this are deleted
_JANITOR_INTERVAL_HOURS: int = 24      # run at most once per this many hours
_JANITOR_STATE_FILE: str = "janitor.json"   # written inside data_dir


class Janitor:
    """Runs one-shot cleanup tasks and records when it last ran.

    Args:
        settings: A settings object (or dict-like) that exposes at minimum:

            - ``data_dir``        – directory for persistent data / databases
            - ``temp_dir``        – directory for temporary files to be purged
            - ``checkpoint_dir``  – directory containing checkpoint JSON files
            - ``databases``       – mapping of logical name → SQLite file path
              (the ``"episodic"`` entry is trimmed if present)
    """

    def __init__(self, settings) -> None:
        self.settings = settings

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Execute all cleanup tasks in sequence."""
        logger.info("Janitor starting …")
        self._clean_temp()
        self._trim_episodic_db()
        self._trim_checkpoints()
        self._record_run()
        logger.info("Janitor finished.")

    def should_run(self) -> bool:
        """Return ``True`` if the janitor has not run within the last 24 hours."""
        state_path = self._state_file_path()
        if not state_path.exists():
            return True

        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            raw = data.get("last_run")
            if not raw:
                return True
            last_run = datetime.fromisoformat(raw)
            # Make timezone-aware if necessary.
            if last_run.tzinfo is None:
                last_run = last_run.replace(tzinfo=timezone.utc)
            threshold = datetime.now(tz=timezone.utc) - timedelta(hours=_JANITOR_INTERVAL_HOURS)
            return last_run < threshold
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            logger.warning("Could not read janitor state file: %s", exc)
            return True

    # ------------------------------------------------------------------
    # Cleanup tasks
    # ------------------------------------------------------------------

    def _clean_temp(self) -> None:
        """Delete files in ``temp_dir`` that are older than 24 hours."""
        temp_dir = Path(self._get("temp_dir", os.path.join("workspace", "temp")))
        if not temp_dir.exists():
            logger.debug("Temp directory does not exist; nothing to clean.")
            return

        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=_TEMP_MAX_AGE_HOURS)
        deleted_files = 0
        deleted_dirs = 0

        for entry in temp_dir.iterdir():
            try:
                mtime = datetime.fromtimestamp(entry.stat().st_mtime, tz=timezone.utc)
            except OSError as exc:
                logger.warning("Cannot stat %s: %s", entry, exc)
                continue

            if mtime >= cutoff:
                continue  # still fresh

            try:
                if entry.is_dir():
                    shutil.rmtree(entry)
                    deleted_dirs += 1
                else:
                    entry.unlink()
                    deleted_files += 1
            except OSError as exc:
                logger.warning("Failed to delete %s: %s", entry, exc)

        logger.info(
            "Temp cleanup: removed %d file(s) and %d directory/ies.",
            deleted_files,
            deleted_dirs,
        )

    def _trim_episodic_db(self) -> None:
        """Keep only the last 1 000 task records in the episodic SQLite database.

        The table is expected to be named ``tasks`` with an integer primary key
        or an ``id`` column.  If the table or database does not exist the
        method logs a debug message and returns without error.
        """
        databases: dict = self._get(
            "databases",
            {
                "episodic": os.path.join("data", "episodic.db"),
            },
        )
        db_path = Path(databases.get("episodic", os.path.join("data", "episodic.db")))

        if not db_path.exists():
            logger.debug("Episodic database does not exist; nothing to trim.")
            return

        try:
            conn = connect(str(db_path), wal=False)
            try:
                cursor = conn.cursor()

                # Determine whether the tasks table exists.
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks';"
                )
                if cursor.fetchone() is None:
                    logger.debug("Episodic DB has no 'tasks' table; skipping trim.")
                    return

                # Count current rows.
                cursor.execute("SELECT COUNT(*) FROM tasks;")
                total: int = cursor.fetchone()[0]

                if total <= _EPISODIC_MAX_ROWS:
                    logger.debug(
                        "Episodic DB has %d row(s) — within limit; no trim needed.", total
                    )
                    return

                # Determine the primary key column name (prefer 'id', then
                # the first column returned by PRAGMA table_info).
                cursor.execute("PRAGMA table_info(tasks);")
                columns = [row[1] for row in cursor.fetchall()]
                pk_col = "id" if "id" in columns else columns[0]

                excess = total - _EPISODIC_MAX_ROWS
                cursor.execute(
                    f"""
                    DELETE FROM tasks
                    WHERE {pk_col} IN (
                        SELECT {pk_col} FROM tasks
                        ORDER BY {pk_col} ASC
                        LIMIT ?
                    )
                    """,
                    (excess,),
                )
                conn.commit()
                logger.info(
                    "Episodic DB trimmed: deleted %d oldest record(s), kept %d.",
                    cursor.rowcount,
                    _EPISODIC_MAX_ROWS,
                )
            finally:
                conn.close()
        except sqlite3.Error as exc:
            logger.warning("Failed to trim episodic database: %s", exc)

    def _trim_checkpoints(self) -> None:
        """Delete *completed* checkpoint files that are older than 7 days.

        Only checkpoints with ``status == "completed"`` are removed; failed
        or in-progress checkpoints are left for operator review.
        """
        checkpoint_dir = Path(
            self._get("checkpoint_dir", os.path.join("data", "checkpoints"))
        )
        if not checkpoint_dir.exists():
            logger.debug("Checkpoint directory does not exist; nothing to trim.")
            return

        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=_CHECKPOINT_MAX_AGE_DAYS)
        deleted = 0

        for cp_file in sorted(checkpoint_dir.glob("*.json")):
            try:
                data = json.loads(cp_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Skipping unreadable checkpoint %s: %s", cp_file.name, exc)
                continue

            if data.get("status") != "completed":
                continue  # only remove completed checkpoints

            # Use the ``completed_at`` field when available; fall back to
            # the file's own modification time.
            raw_ts = data.get("completed_at")
            if raw_ts:
                try:
                    ts = datetime.fromisoformat(raw_ts)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                except ValueError:
                    ts = None
            else:
                ts = None

            if ts is None:
                try:
                    ts = datetime.fromtimestamp(cp_file.stat().st_mtime, tz=timezone.utc)
                except OSError:
                    ts = datetime.now(tz=timezone.utc)  # assume current → skip

            if ts >= cutoff:
                continue  # still within retention window

            try:
                cp_file.unlink()
                deleted += 1
                logger.debug("Deleted old checkpoint: %s", cp_file.name)
            except OSError as exc:
                logger.warning("Could not delete checkpoint %s: %s", cp_file.name, exc)

        logger.info("Checkpoint trim: deleted %d completed checkpoint file(s).", deleted)

    def _record_run(self) -> None:
        """Write the current UTC timestamp to ``data/janitor.json``."""
        state_path = self._state_file_path()
        state_path.parent.mkdir(parents=True, exist_ok=True)

        now_iso = datetime.now(tz=timezone.utc).isoformat()
        payload = {"last_run": now_iso}
        try:
            state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            logger.debug("Janitor state written to %s (last_run=%s)", state_path, now_iso)
        except OSError as exc:
            logger.warning("Could not write janitor state file: %s", exc)

    # ------------------------------------------------------------------
    # Internal utilities
    # ------------------------------------------------------------------

    def _state_file_path(self) -> Path:
        """Return the absolute path to the janitor state JSON file."""
        data_dir = Path(self._get("data_dir", "data"))
        return data_dir / _JANITOR_STATE_FILE

    def _get(self, key: str, default=None):
        """Retrieve a value from settings, supporting both dict and object APIs."""
        if isinstance(self.settings, dict):
            return self.settings.get(key, default)
        return getattr(self.settings, key, default)
