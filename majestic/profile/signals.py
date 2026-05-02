"""Collect interaction signals after each session — zero LLM calls."""
import json
import re
import threading
from pathlib import Path
from datetime import datetime, timezone

from majestic.constants import MAJESTIC_HOME

_SIGNALS_FILE = MAJESTIC_HOME / "profile_signals.jsonl"
_MAX_LINES = 50
_lock = threading.Lock()


def collect_signals(session_id: str) -> None:
    """Read the just-finished session from DB and append a signal record."""
    try:
        from majestic.db.state import StateDB
        msgs = StateDB().get_session_messages(session_id, limit=100)
    except Exception:
        return

    user_msgs = [m for m in msgs if m["role"] == "user"]
    assistant_msgs = [m for m in msgs if m["role"] == "assistant"]
    tool_msgs = [m for m in msgs if m["role"] == "tool"]

    if not user_msgs:
        return

    # Language detection — simple heuristic
    all_user_text = " ".join(m["content"] for m in user_msgs)
    cyrillic = len(re.findall(r"[а-яёА-ЯЁ]", all_user_text))
    latin = len(re.findall(r"[a-zA-Z]", all_user_text))
    if cyrillic > latin * 1.5:
        lang = "ru"
    elif latin > cyrillic * 1.5:
        lang = "en"
    else:
        lang = "mix"

    # Tool names used
    tools_used = list({m["content"].split(":")[0].strip() for m in tool_msgs if m["content"]})

    # Keyword extraction — top words from user messages (len > 4)
    words = re.findall(r"\b\w{5,}\b", all_user_text.lower())
    freq: dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    top_keywords = sorted(freq, key=lambda k: -freq[k])[:8]

    signal = {
        "session_id": session_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "lang": lang,
        "user_msg_count": len(user_msgs),
        "avg_user_len": int(sum(len(m["content"]) for m in user_msgs) / len(user_msgs)),
        "avg_assistant_len": int(sum(len(m["content"]) for m in assistant_msgs) / max(len(assistant_msgs), 1)),
        "tools_used": tools_used,
        "keywords": top_keywords,
    }

    with _lock:
        MAJESTIC_HOME.mkdir(parents=True, exist_ok=True)
        lines = []
        if _SIGNALS_FILE.exists():
            lines = _SIGNALS_FILE.read_text(encoding="utf-8").splitlines()
        lines.append(json.dumps(signal, ensure_ascii=False))
        # Keep only the last _MAX_LINES
        _SIGNALS_FILE.write_text("\n".join(lines[-_MAX_LINES:]) + "\n", encoding="utf-8")

    # Check whether it's time to update the profile
    from majestic.profile.updater import maybe_update_profile
    maybe_update_profile()
