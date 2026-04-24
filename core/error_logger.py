"""
Error logger — only important / actionable errors.
Persisted to data/logs/errors.json (newest first, max 100).

Call log_error() for errors worth surfacing to the user:
  - Failed to fetch/parse a source (HN, Reddit, GitHub, etc.)
  - LLM call failed
  - Market data unavailable
  - File indexing failed

NOT for: routine debug info, expected HTTP 429 retries, warnings.

Usage:
  from core.error_logger import log_error
  log_error("intel.hackernews", "Failed to fetch HN", str(e))
"""
import json
from datetime import datetime
from pathlib import Path
from threading import Lock

_LOG_PATH   = Path(__file__).parent.parent / "data" / "logs" / "errors.json"
_lock       = Lock()
_MAX_ERRORS = 100


def log_error(source: str, message: str, detail: str = ""):
    """
    Log an actionable error.

    Args:
        source:  module/subsystem, e.g. "intel.hackernews", "llm.briefing"
        message: short description, e.g. "Failed to fetch HN"
        detail:  exception str or extra context (truncated to 300 chars)
    """
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
    """Return last N error entries, newest first."""
    if not _LOG_PATH.exists():
        return []
    try:
        return json.loads(_LOG_PATH.read_text(encoding="utf-8"))[:limit]
    except Exception:
        return []


def clear_errors():
    """Remove all logged errors."""
    if _LOG_PATH.exists():
        _LOG_PATH.write_text("[]", encoding="utf-8")


def format_errors(limit: int = 15) -> str:
    """Return a formatted string of recent errors for CLI/Telegram display."""
    errors = get_errors(limit)
    if not errors:
        return "✅ No errors logged."

    today = datetime.now().date()
    lines = [f"⚠️ Recent errors ({len(errors)} shown):"]

    # Display oldest first so newest appears at bottom
    for e in reversed(errors):
        try:
            ts = datetime.fromisoformat(e["ts"])
            date_label = "today" if ts.date() == today else ts.strftime("%m-%d")
            time_label = ts.strftime("%H:%M")
            ts_str = f"{date_label} {time_label}"
        except Exception:
            ts_str = e.get("ts", "?")

        source  = e.get("source", "?")
        message = e.get("message", "?")
        detail  = e.get("detail", "")

        lines.append(f"\n[{ts_str}] {source}")
        lines.append(f"  {message}")
        if detail:
            lines.append(f"  → {detail[:120]}")

    return "\n".join(lines)
