"""Update user_profile.yaml via a single LLM call every N sessions."""
import json
import threading
from pathlib import Path
from datetime import datetime, timezone

import yaml

from majestic.constants import MAJESTIC_HOME

_PROFILE_FILE = MAJESTIC_HOME / "user_profile.yaml"
_SIGNALS_FILE = MAJESTIC_HOME / "profile_signals.jsonl"
_lock = threading.Lock()
_DEFAULT_UPDATE_EVERY = 10


def _load_profile() -> dict:
    if not _PROFILE_FILE.exists():
        return {"sessions_since_update": 0}
    try:
        return yaml.safe_load(_PROFILE_FILE.read_text(encoding="utf-8")) or {}
    except Exception:
        return {"sessions_since_update": 0}


def _save_profile(profile: dict) -> None:
    MAJESTIC_HOME.mkdir(parents=True, exist_ok=True)
    _PROFILE_FILE.write_text(
        yaml.dump(profile, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def maybe_update_profile() -> None:
    """Increment session counter; if threshold reached, trigger LLM update in background."""
    with _lock:
        profile = _load_profile()
        count = profile.get("sessions_since_update", 0) + 1
        profile["sessions_since_update"] = count
        _save_profile(profile)

    try:
        from majestic.config import get as cfg_get
        update_every = int(cfg_get("profile.update_every", _DEFAULT_UPDATE_EVERY))
        enabled = cfg_get("profile.enabled", True)
    except Exception:
        update_every = _DEFAULT_UPDATE_EVERY
        enabled = True

    if not enabled or count < update_every:
        return

    threading.Thread(target=_run_update, daemon=True).start()


def _run_update() -> None:
    """One LLM call to analyse signals and rewrite user_profile.yaml."""
    try:
        if not _SIGNALS_FILE.exists():
            return

        lines = _SIGNALS_FILE.read_text(encoding="utf-8").splitlines()
        signals = []
        for line in lines[-_DEFAULT_UPDATE_EVERY:]:
            try:
                signals.append(json.loads(line))
            except Exception:
                pass

        if not signals:
            return

        summary = json.dumps(signals, ensure_ascii=False, indent=2)
        prompt = (
            "You are analysing interaction signals from an AI assistant. "
            "Based on these signals, produce a compact YAML user profile. "
            "Output ONLY valid YAML, no prose, no code fences.\n\n"
            "Required keys: language (ru/en/mix), tone (formal/informal), "
            "response_style (concise/detailed), interests (list of topics), "
            "preferred_tools (list), notes (1 short sentence about the user).\n\n"
            f"Signals (last sessions):\n{summary}"
        )

        from majestic.llm import get_provider
        resp = get_provider().complete(
            messages=[{"role": "user", "content": prompt}],
            system="You output structured YAML only.",
            max_tokens=512,
        )

        raw = resp.content.strip()
        # Strip code fences if model added them
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
        if raw.endswith("```"):
            raw = "\n".join(raw.split("\n")[:-1])

        new_profile = yaml.safe_load(raw) or {}
        new_profile["updated_at"] = datetime.now(timezone.utc).isoformat()
        new_profile["sessions_since_update"] = 0

        with _lock:
            _save_profile(new_profile)

    except Exception:
        # Silently fail — profile update is best-effort
        pass


def get_profile_block() -> str:
    """Return a compact [User profile] string for injection into the system prompt."""
    try:
        profile = _load_profile()
        if not profile or list(profile.keys()) == ["sessions_since_update"]:
            return ""

        parts = []
        if lang := profile.get("language"):
            parts.append(f"Language: {lang}")
        if tone := profile.get("tone"):
            parts.append(f"Tone: {tone}")
        if style := profile.get("response_style"):
            parts.append(f"Response style: {style}")
        if interests := profile.get("interests"):
            parts.append(f"Interests: {', '.join(interests[:5])}")
        if tools := profile.get("preferred_tools"):
            parts.append(f"Often uses: {', '.join(tools[:4])}")
        if notes := profile.get("notes"):
            parts.append(f"Note: {notes}")

        return "\n".join(parts) if parts else ""
    except Exception:
        return ""
