"""Post-session reflection — extracts learnings in a background LLM call."""
from __future__ import annotations

import threading

_PROMPT = """\
Review this agent session. Extract 5-8 concrete, actionable bullet points.
Cover: user's goal, what worked, what failed/retried, any reusable pattern (→ save_script?), any preference observed.
Be specific. No preamble. Bullet list only.

Session:
{session_text}
"""


def reflect_session(session_id: str, answer: str, tool_names: list[str]) -> None:
    """Fire-and-forget: run reflection in a daemon thread."""
    def _run():
        try:
            _do_reflect(session_id, answer, tool_names)
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


def _do_reflect(session_id: str, answer: str, tool_names: list[str]) -> None:
    from majestic.constants import WORKSPACE_DIR
    from majestic.llm import get_provider

    text = _build_session_text(session_id, answer, tool_names)
    if not text:
        return

    provider = get_provider()
    resp = provider.complete(
        messages=[{"role": "user", "content": _PROMPT.format(session_text=text)}],
        system="You are a concise analyst extracting actionable learnings from AI agent sessions.",
        max_tokens=512,
        tools=None,
    )
    content = (resp.content or "").strip()
    if not content:
        return

    out_dir = WORKSPACE_DIR / ".reflections"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{session_id}.md").write_text(content, encoding="utf-8")


def _build_session_text(session_id: str, answer: str, tool_names: list[str]) -> str:
    try:
        from majestic.db.state import StateDB
        msgs = StateDB().get_session_messages(session_id, limit=20)
        user_msgs = [m["content"][:200] for m in msgs if m.get("role") == "user"]
        tools_str = ", ".join(dict.fromkeys(tool_names))
        lines = []
        if user_msgs:
            lines.append("User requests: " + " | ".join(user_msgs[:3]))
        lines.append(f"Tools used: {tools_str or 'none'}")
        lines.append(f"Final answer (excerpt): {answer[:300]}")
        return "\n".join(lines)
    except Exception:
        return ""


def get_recent_learnings() -> str:
    """Return compact summary of last 5 reflections for system prompt injection."""
    try:
        from majestic.constants import WORKSPACE_DIR
        d = WORKSPACE_DIR / ".reflections"
        if not d.exists():
            return ""
        files = sorted(d.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]
        parts = []
        for f in files:
            lines = f.read_text(encoding="utf-8").strip().splitlines()
            excerpt = "\n".join(lines[:3])
            parts.append(f"[session {f.stem[:8]}]\n{excerpt}")
        return "\n\n".join(parts)
    except Exception:
        return ""
