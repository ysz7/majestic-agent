"""Error logger — actionable errors only, persisted to MAJESTIC_HOME/errors.json."""
from __future__ import annotations

import json
from datetime import datetime
from threading import Lock

from majestic.constants import MAJESTIC_HOME

_LOG_PATH   = MAJESTIC_HOME / "errors.json"
_lock       = Lock()
_MAX_ERRORS = 100


def log_error(source: str, message: str, detail: str = "") -> None:
    entry = {
        "ts":      datetime.now().isoformat(timespec="seconds"),
        "source":  source,
        "message": message,
        "detail":  str(detail)[:300] if detail else "",
    }
    with _lock:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        errors: list = []
        if _LOG_PATH.exists():
            try:
                errors = json.loads(_LOG_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        errors = ([entry] + errors)[:_MAX_ERRORS]
        _LOG_PATH.write_text(json.dumps(errors, indent=2, ensure_ascii=False), encoding="utf-8")


def get_errors(limit: int = 20) -> list:
    if not _LOG_PATH.exists():
        return []
    try:
        return json.loads(_LOG_PATH.read_text(encoding="utf-8"))[:limit]
    except Exception:
        return []


def format_errors(limit: int = 15) -> str:
    errors = get_errors(limit)
    if not errors:
        return "No errors logged."
    today = datetime.now().date()
    lines = [f"Recent errors ({len(errors)} shown):"]
    for e in reversed(errors):
        try:
            ts     = datetime.fromisoformat(e["ts"])
            ts_str = ("today " if ts.date() == today else ts.strftime("%m-%d ")) + ts.strftime("%H:%M")
        except Exception:
            ts_str = e.get("ts", "?")
        lines.append(f"\n[{ts_str}] {e.get('source', '?')}")
        lines.append(f"  {e.get('message', '?')}")
        if e.get("detail"):
            lines.append(f"  → {e['detail'][:120]}")
    return "\n".join(lines)
