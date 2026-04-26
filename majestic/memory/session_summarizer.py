"""
Summarize a session into one sentence after it ends.
Runs in a background thread on /exit so it doesn't block the user.
"""
import threading

_PROMPT = """\
Summarize this conversation in ONE short sentence (max 15 words).
Focus on what the user asked and what was accomplished.
Reply with ONLY the sentence, no punctuation at the end.

Conversation:
{messages}"""


def summarize_session(session_id: str) -> None:
    """Start background summarization of the given session."""
    threading.Thread(
        target=_run,
        args=(session_id,),
        daemon=True,
        name="session-summarizer",
    ).start()


def _run(session_id: str) -> None:
    try:
        from majestic.db.state import StateDB
        db = StateDB()
        msgs = db.get_session_messages(session_id, limit=30)
        if not msgs:
            return

        lines = [
            f"{m['role'].upper()}: {m['content'][:200]}"
            for m in msgs
            if m["role"] in ("user", "assistant") and m["content"].strip()
        ]
        if not lines:
            return

        from majestic.llm import get_provider
        prompt = _PROMPT.format(messages="\n".join(lines[:20]))
        resp = get_provider().complete([{"role": "user", "content": prompt}])
        title = resp.content.strip().strip(".")[:120]
        if title:
            db.set_session_title(session_id, title)
    except Exception:
        pass
