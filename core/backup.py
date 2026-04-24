"""
ChromaDB backup system.

Logic:
- Backup metadata stored in data/backups/last_backup.json
- If more than 1 day since last backup → create new backup
- Keep only the last 7 backups (older ones are deleted)
- check_and_backup() is safe to call on every start and from a scheduler
- start_backup_scheduler() runs check on start, then every 24h in background
"""
import json
import logging
import threading
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────
_BASE_DIR    = Path(__file__).parent.parent / "data"
_DB_DIR      = _BASE_DIR / "vector_db"
_BACKUP_DIR  = _BASE_DIR / "backups"
_META_FILE   = _BACKUP_DIR / "last_backup.json"

_BACKUP_INTERVAL_HOURS = 24
_KEEP_BACKUPS          = 7


# ── Metadata ───────────────────────────────────────────────────────────────────

def _read_meta() -> dict:
    if _META_FILE.exists():
        try:
            return json.loads(_META_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _write_meta(meta: dict):
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    _META_FILE.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def last_backup_time() -> datetime | None:
    """Return datetime of last successful backup, or None if never backed up."""
    ts = _read_meta().get("last_backup")
    if ts:
        try:
            return datetime.fromisoformat(ts)
        except Exception:
            pass
    return None


# ── Core backup logic ──────────────────────────────────────────────────────────

def backup_now() -> Path:
    """
    Create a zip of data/vector_db/ in data/backups/.
    Returns path to the created zip file.
    """
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = _BACKUP_DIR / f"vector_db_{ts}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in _DB_DIR.rglob("*"):
            if file.is_file():
                zf.write(file, file.relative_to(_DB_DIR))

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    logger.info(f"[backup] Created: {zip_path.name} ({size_mb:.1f} MB)")

    # Save metadata
    _write_meta({
        "last_backup":      datetime.now().isoformat(),
        "last_backup_file": zip_path.name,
        "size_mb":          round(size_mb, 2),
    })

    _cleanup_old_backups()
    return zip_path


def _cleanup_old_backups():
    """Delete backups older than the last N, keeping _KEEP_BACKUPS most recent."""
    backups = sorted(_BACKUP_DIR.glob("vector_db_*.zip"), key=lambda f: f.stat().st_mtime)
    to_delete = backups[:-_KEEP_BACKUPS] if len(backups) > _KEEP_BACKUPS else []
    for f in to_delete:
        try:
            f.unlink()
            logger.info(f"[backup] Deleted old backup: {f.name}")
        except Exception as e:
            logger.warning(f"[backup] Could not delete {f.name}: {e}")


# ── Check & trigger ────────────────────────────────────────────────────────────

def check_and_backup() -> bool:
    """
    Check if a backup is due and run it if needed.
    Returns True if a backup was created, False if skipped.

    A backup is due when:
    - No backup has ever been made, OR
    - More than _BACKUP_INTERVAL_HOURS have passed since the last backup
    """
    if not _DB_DIR.exists() or not any(_DB_DIR.iterdir()):
        logger.debug("[backup] vector_db is empty, skipping")
        return False

    last = last_backup_time()
    if last is None:
        logger.info("[backup] No previous backup found — creating first backup")
    elif datetime.now() - last >= timedelta(hours=_BACKUP_INTERVAL_HOURS):
        hours_ago = (datetime.now() - last).total_seconds() / 3600
        logger.info(f"[backup] Last backup was {hours_ago:.1f}h ago — creating backup")
    else:
        remaining = timedelta(hours=_BACKUP_INTERVAL_HOURS) - (datetime.now() - last)
        hours_left = remaining.total_seconds() / 3600
        logger.debug(f"[backup] Next backup in {hours_left:.1f}h — skipping")
        return False

    try:
        backup_now()
        return True
    except Exception as e:
        logger.error(f"[backup] Backup failed: {e}")
        return False


# ── Background scheduler ───────────────────────────────────────────────────────

def start_backup_scheduler():
    """
    Start a background thread that:
    1. Runs check_and_backup() immediately on start
    2. Then checks every hour (actual backup only triggers if 24h elapsed)

    Safe to call multiple times — only one scheduler thread runs.
    """
    def _loop():
        while True:
            try:
                check_and_backup()
            except Exception as e:
                logger.error(f"[backup] Scheduler error: {e}")
            time.sleep(3600)  # check every hour

    t = threading.Thread(target=_loop, daemon=True, name="backup-scheduler")
    t.start()
    logger.info("[backup] Scheduler started (checks every 1h, backs up every 24h)")


# ── Status info ────────────────────────────────────────────────────────────────

def backup_status() -> dict:
    """Return current backup status as a dict (for /stats display)."""
    meta = _read_meta()
    backups = sorted(_BACKUP_DIR.glob("vector_db_*.zip"), key=lambda f: f.stat().st_mtime, reverse=True)
    last = last_backup_time()
    next_backup = None
    if last:
        nxt = last + timedelta(hours=_BACKUP_INTERVAL_HOURS)
        next_backup = nxt.strftime("%Y-%m-%d %H:%M") if nxt > datetime.now() else "due now"

    return {
        "last_backup":      meta.get("last_backup", "never"),
        "last_backup_file": meta.get("last_backup_file", "—"),
        "size_mb":          meta.get("size_mb", 0),
        "total_backups":    len(backups),
        "next_backup":      next_backup or "now",
    }
