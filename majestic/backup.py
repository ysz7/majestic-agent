"""
Backup — zip MAJESTIC_HOME daily, keep last 7.
Safe to call multiple times: only backs up if 24h have elapsed.
"""
from __future__ import annotations

import logging
import threading
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from majestic.constants import MAJESTIC_HOME

_BACKUP_DIR      = MAJESTIC_HOME / "backups"
_META_FILE       = _BACKUP_DIR / "last_backup.json"
_INTERVAL_HOURS  = 24
_KEEP            = 7
logger           = logging.getLogger(__name__)


def _read_meta() -> dict:
    if _META_FILE.exists():
        try:
            import json
            return json.loads(_META_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _write_meta(meta: dict) -> None:
    import json
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    _META_FILE.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def backup_now() -> Path:
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = _BACKUP_DIR / f"majestic_{ts}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in MAJESTIC_HOME.rglob("*"):
            if f.is_file() and f != zip_path and "backups" not in f.parts:
                zf.write(f, f.relative_to(MAJESTIC_HOME))
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    _write_meta({"last_backup": datetime.now().isoformat(),
                 "last_backup_file": zip_path.name, "size_mb": round(size_mb, 2)})
    _cleanup()
    logger.info(f"[backup] {zip_path.name} ({size_mb:.1f} MB)")
    return zip_path


def _cleanup() -> None:
    backups = sorted(_BACKUP_DIR.glob("majestic_*.zip"), key=lambda f: f.stat().st_mtime)
    for f in backups[:-_KEEP]:
        try:
            f.unlink()
        except Exception:
            pass


def check_and_backup() -> bool:
    last_ts = _read_meta().get("last_backup")
    if last_ts:
        last = datetime.fromisoformat(last_ts)
        if datetime.now() - last < timedelta(hours=_INTERVAL_HOURS):
            return False
    try:
        backup_now()
        return True
    except Exception as e:
        logger.error(f"[backup] failed: {e}")
        return False


_started = False


def start_backup_scheduler() -> None:
    global _started
    if _started:
        return
    _started = True

    def _loop():
        while True:
            try:
                check_and_backup()
            except Exception as e:
                logger.error(f"[backup] {e}")
            time.sleep(3600)

    threading.Thread(target=_loop, daemon=True, name="backup-scheduler").start()
