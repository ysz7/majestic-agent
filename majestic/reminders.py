"""
Reminders — natural language date parsing + persistent storage + background watcher.

Storage: MAJESTIC_HOME/reminders.json
"""
from __future__ import annotations

import json
import platform
import re
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from majestic.constants import MAJESTIC_HOME

_FILE = MAJESTIC_HOME / "reminders.json"

_DATEPARSER_SETTINGS = {
    "LANGUAGES": ["ru", "en"],
    "PREFER_DATES_FROM": "future",
    "RETURN_AS_TIMEZONE_AWARE": False,
}


def _load() -> list:
    if _FILE.exists():
        try:
            return json.loads(_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save(reminders: list) -> None:
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    _FILE.write_text(json.dumps(reminders, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def parse_date(text: str) -> Optional[datetime]:
    replacements = {
        r"\bзавтра\b": "tomorrow", r"\bсегодня\b": "today",
        r"\bпослезавтра\b": "in 2 days", r"\bчерез неделю\b": "in 1 week",
        r"\bчерез месяц\b": "in 1 month", r"\bчерез час\b": "in 1 hour",
        r"\bчерез (\d+) час": r"in \1 hours", r"\bчерез (\d+) мин": r"in \1 minutes",
    }
    normalized = text.lower()
    for pat, rep in replacements.items():
        normalized = re.sub(pat, rep, normalized)
    try:
        import dateparser
        settings = {**_DATEPARSER_SETTINGS, "RELATIVE_BASE": datetime.now()}
        return dateparser.parse(normalized, settings=settings) or dateparser.parse(text, settings=settings)
    except Exception:
        return None


def add_reminder(text: str, dt: Optional[datetime] = None) -> dict:
    if dt is None:
        dt = parse_date(text)
    if dt is None:
        raise ValueError(f"Could not parse date from: {text!r}")
    reminders = _load()
    entry = {
        "id":      f"r{int(datetime.now().timestamp())}",
        "text":    text,
        "dt":      dt.isoformat(),
        "done":    False,
        "created": datetime.now().isoformat(),
    }
    reminders.append(entry)
    _save(reminders)
    return entry


def list_reminders(include_done: bool = False) -> list:
    items = _load()
    if not include_done:
        items = [r for r in items if not r.get("done")]
    return sorted(items, key=lambda x: x.get("dt", ""))


def mark_done(rid: str) -> None:
    reminders = _load()
    for r in reminders:
        if r["id"] == rid:
            r["done"] = True
    _save(reminders)


def due_reminders() -> list:
    now    = datetime.now()
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


def _notify_system(title: str, message: str) -> None:
    try:
        if platform.system() == "Darwin":
            subprocess.run(["osascript", "-e", f'display notification "{message}" with title "{title}"'], check=False)
        elif platform.system() == "Linux":
            subprocess.run(["notify-send", "-u", "normal", "-t", "8000", title, message], check=False)
    except Exception:
        pass


_notified: set = set()
_watcher_started = False


def start_watcher(on_due=None) -> None:
    global _watcher_started
    if _watcher_started:
        return
    _watcher_started = True

    def _loop():
        while True:
            for r in due_reminders():
                if r["id"] not in _notified:
                    _notified.add(r["id"])
                    _notify_system("⏰ Majestic", r.get("text", "Reminder"))
                    mark_done(r["id"])
                    if on_due:
                        try:
                            on_due(r)
                        except Exception:
                            pass
            time.sleep(30)

    threading.Thread(target=_loop, daemon=True, name="reminders-watcher").start()


def extract_reminder_intent(text: str) -> Optional[dict]:
    """Try to extract a reminder title and datetime from natural language text. Returns {title, dt} or None."""
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
            dt  = parse_date(raw)
            if dt:
                title = re.sub(
                    r"(завтра|сегодня|послезавтра|через .+?|в \d{1,2}[:.]\d{2}|"
                    r"tomorrow|today|in \d+ \w+|on \w+)",
                    "", raw, flags=re.IGNORECASE
                ).strip(" —-–:,")
                return {"title": title or raw, "dt": dt}
    # fallback: try parsing the whole text as a date
    dt = parse_date(text)
    if dt:
        return {"title": text, "dt": dt}
    return None


def format_reminder(r: dict) -> str:
    try:
        dt_str = datetime.fromisoformat(r["dt"]).strftime("%d.%m.%Y %H:%M")
    except Exception:
        dt_str = r.get("dt", "")
    status = "✅" if r.get("done") else "🔔"
    return f"{status} **{r.get('text', '')}**  `{dt_str}`"
