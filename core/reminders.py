"""
Reminders & Date Parser
- Parses dates/times from free text (Russian + English)
- Stores reminders in a JSON file
- Sends system notifications (macOS / Linux)
- Returns a list of active reminders
"""

import json
import re
import subprocess
import platform
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import dateparser

REMINDERS_FILE = Path(__file__).parent.parent / "data" / "reminders.json"
REMINDERS_FILE.parent.mkdir(parents=True, exist_ok=True)


# ── Storage ────────────────────────────────────────────────────────────────────

def _load() -> list:
    if REMINDERS_FILE.exists():
        try:
            return json.loads(REMINDERS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save(reminders: list):
    REMINDERS_FILE.write_text(
        json.dumps(reminders, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


# ── Date parsing ───────────────────────────────────────────────────────────────

DATEPARSER_SETTINGS = {
    "LANGUAGES": ["ru", "en"],
    "PREFER_DATES_FROM": "future",
    "RETURN_AS_TIMEZONE_AWARE": False,
    "RELATIVE_BASE": datetime.now(),
}


def parse_date(text: str) -> Optional[datetime]:
    """Parse a natural language date string. Returns datetime or None."""
    # Normalize common Russian shortcuts
    replacements = {
        r"\bзавтра\b": "tomorrow",
        r"\bсегодня\b": "today",
        r"\bпослезавтра\b": "in 2 days",
        r"\bчерез неделю\b": "in 1 week",
        r"\bчерез месяц\b": "in 1 month",
        r"\bчерез час\b": "in 1 hour",
        r"\bчерез (\d+) час": r"in \1 hours",
        r"\bчерез (\d+) мин": r"in \1 minutes",
    }
    normalized = text.lower()
    for pattern, replacement in replacements.items():
        normalized = re.sub(pattern, replacement, normalized)

    parsed = dateparser.parse(normalized, settings=DATEPARSER_SETTINGS)
    if parsed is None:
        # fallback: try original
        parsed = dateparser.parse(text, settings=DATEPARSER_SETTINGS)
    return parsed


def extract_reminder_intent(text: str) -> Optional[dict]:
    """
    Try to extract a reminder from a chat message.
    Returns {title, dt} or None.
    Example inputs:
      "Напомни мне завтра в 10:00 позвонить Ивану"
      "Remind me in 2 hours to check email"
      "Поставь напоминание на пятницу 15:00 — встреча с командой"
    """
    patterns = [
        r"напомни(?:те)?\s+(?:мне\s+)?(.+?)(?:\s+(?:в|at)\s+(\d{1,2}[:.]\d{2}))?$",
        r"remind\s+me\s+(.+)",
        r"напоминани[ея]\s+(?:на\s+)?(.+)",
        r"поставь\s+напоминани[ея]\s+(?:на\s+)?(.+)",
    ]

    for pat in patterns:
        m = re.search(pat, text.strip(), re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            dt = parse_date(raw)
            if dt:
                # title = whatever remains after removing the date part
                title = re.sub(
                    r"(завтра|сегодня|послезавтра|через .+?|в \d{1,2}[:.]\d{2}|"
                    r"tomorrow|today|in \d+ \w+|on \w+)",
                    "", raw, flags=re.IGNORECASE
                ).strip(" —-–:,")
                title = title or raw
                return {"title": title, "dt": dt}
    return None


# ── Reminders CRUD ─────────────────────────────────────────────────────────────

def add_reminder(title: str, dt: datetime, note: str = "") -> dict:
    reminders = _load()
    rid = f"r{int(datetime.now().timestamp())}"
    entry = {
        "id":      rid,
        "title":   title,
        "dt":      dt.isoformat(),
        "note":    note,
        "done":    False,
        "created": datetime.now().isoformat(),
    }
    reminders.append(entry)
    _save(reminders)
    return entry


def list_reminders(include_done: bool = False) -> list:
    reminders = _load()
    if not include_done:
        reminders = [r for r in reminders if not r.get("done")]
    return sorted(reminders, key=lambda x: x["dt"])


def mark_done(rid: str):
    reminders = _load()
    for r in reminders:
        if r["id"] == rid:
            r["done"] = True
    _save(reminders)


def delete_reminder(rid: str):
    reminders = [r for r in _load() if r["id"] != rid]
    _save(reminders)


def due_reminders() -> list:
    """Return reminders that are due now (within last 2 minutes)."""
    now = datetime.now()
    window = timedelta(minutes=2)
    result = []
    for r in list_reminders():
        try:
            dt = datetime.fromisoformat(r["dt"])
            if now - window <= dt <= now + timedelta(seconds=30):
                result.append(r)
        except Exception:
            pass
    return result


# ── System notifications ───────────────────────────────────────────────────────

def _notify_system(title: str, message: str):
    system = platform.system()
    try:
        if system == "Darwin":  # macOS
            script = f'display notification "{message}" with title "{title}" sound name "Glass"'
            subprocess.run(["osascript", "-e", script], check=False)
        elif system == "Linux":
            subprocess.run(
                ["notify-send", "-u", "normal", "-t", "8000", title, message],
                check=False,
            )
    except Exception as e:
        print(f"[notify] {e}")


# ── Background watcher ─────────────────────────────────────────────────────────

_notified: set = set()   # track already-notified reminder IDs
_watcher_started = False


def _watch_loop(on_due=None):
    """Check reminders every 30 seconds. Call on_due(reminder) if provided."""
    global _notified
    while True:
        for r in due_reminders():
            if r["id"] not in _notified:
                _notified.add(r["id"])
                _notify_system("⏰ Parallax", r["title"])
                mark_done(r["id"])
                if on_due:
                    try:
                        on_due(r)
                    except Exception:
                        pass
        time.sleep(30)


def start_watcher(on_due=None):
    global _watcher_started
    if _watcher_started:
        return
    _watcher_started = True
    t = threading.Thread(target=_watch_loop, args=(on_due,), daemon=True)
    t.start()


# ── Formatting helpers ─────────────────────────────────────────────────────────

def format_reminder(r: dict) -> str:
    try:
        dt = datetime.fromisoformat(r["dt"])
        dt_str = dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        dt_str = r["dt"]
    status = "✅" if r.get("done") else "🔔"
    note = f" — {r['note']}" if r.get("note") else ""
    return f"{status} **{r['title']}**  `{dt_str}`{note}"


def reminders_summary() -> str:
    items = list_reminders()
    if not items:
        return "📭 No active reminders."
    lines = [f"**Active reminders ({len(items)}):**\n"]
    for r in items:
        lines.append(format_reminder(r))
    return "\n".join(lines)
