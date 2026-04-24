"""
After each session the agent reviews the conversation and decides what to remember.
Runs in a background thread — never blocks the user.

Writes to:
  memory.md — facts, insights, tasks learned during the session
  user.md   — new things learned about the user (preferences, background, etc.)
"""
import threading
from typing import Optional

_NUDGE_PROMPT = """You are a memory manager for an AI agent called Majestic.

Review this conversation and extract information worth remembering for future sessions.

Conversation:
{history}

---

Decide what to save. Respond with a JSON object:
{{
  "memory": ["fact or insight worth keeping long-term", ...],
  "user":   ["something new learned about the user", ...]
}}

Rules:
- Only include genuinely new, non-obvious, durable facts
- Skip anything that's ephemeral (e.g. "user asked about X today")
- Skip anything already obvious from context
- If nothing worth saving: return empty lists
- Each entry should be a self-contained sentence or bullet point
- Max 3 entries per category

Respond ONLY with the JSON, no explanation.
"""


def _run_nudge(history: list[tuple[str, str]], lang: str = "EN") -> None:
    """Called in background thread. Writes to memory files."""
    if not history:
        return

    history_text = "\n\n".join(
        f"User: {u}\nAssistant: {a}" for u, a in history[-10:]
    )

    try:
        import json
        from core.rag_engine import llm
        from langchain_core.messages import HumanMessage
        from majestic.memory.store import append_memory, append_user

        prompt = _NUDGE_PROMPT.format(history=history_text)
        if lang != "EN":
            prompt += f"\n\nNote: entries should be written in {lang}."

        response = llm.invoke([HumanMessage(content=prompt)])
        text = response.content.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]

        data = json.loads(text)
        for entry in data.get("memory", []):
            if entry.strip():
                append_memory(f"- {entry.strip()}")
        for entry in data.get("user", []):
            if entry.strip():
                append_user(f"- {entry.strip()}")

    except Exception as e:
        # Nudge is best-effort — never crash the main thread
        print(f"[memory nudge] {e}")


def nudge_after_session(
    history: list[tuple[str, str]],
    lang: str = "EN",
    blocking: bool = False,
) -> Optional[threading.Thread]:
    """
    Trigger memory update after a session ends.
    By default runs in background (non-blocking).
    Returns the thread (or None if history is empty).
    """
    if not history:
        return None
    t = threading.Thread(
        target=_run_nudge,
        args=(history, lang),
        daemon=True,
        name="memory-nudge",
    )
    t.start()
    if blocking:
        t.join(timeout=30)
    return t
