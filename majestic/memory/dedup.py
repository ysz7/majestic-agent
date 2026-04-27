"""
LLM-based memory deduplication — one call on session exit.

Scans both memory files for duplicate or contradictory entries and
merges them. Only triggers when combined memory exceeds 600 chars.
"""
from __future__ import annotations

_PROMPT = """\
You are cleaning up an AI agent's persistent memory.
Below are the current contents of two memory files.
Task: find and merge duplicate or contradictory entries.
Rules:
- Keep all unique, useful information
- Remove true duplicates (same fact stated twice)
- Resolve contradictions (keep the most recent/specific version)
- Preserve original language and style
- Do NOT add new information

Memory files:

[AGENT MEMORY]
{agent_mem}

[USER PROFILE]
{user_mem}

Return ONLY the cleaned content in this exact format (use empty section if nothing remains):

[AGENT MEMORY]
<cleaned agent memory>

[USER PROFILE]
<cleaned user profile>
"""


def dedup_memory() -> bool:
    """
    Run one LLM call to dedup and merge memory files.
    Returns True if any changes were written.
    """
    try:
        from majestic.memory.store import (
            load_memory, load_user,
            MEMORY_FILE, USER_FILE,
            _MEMORY_HEADER, _USER_HEADER,
        )
        mem  = load_memory()
        user = load_user()

        if len(mem) + len(user) < 600:
            return False

        from majestic.llm import get_provider
        prompt = _PROMPT.format(agent_mem=mem or "(empty)", user_mem=user or "(empty)")
        resp   = get_provider().complete([{"role": "user", "content": prompt}])
        text   = (resp.content or "").strip()
        if not text:
            return False

        new_mem  = _extract(text, "[AGENT MEMORY]", "[USER PROFILE]")
        new_user = _extract(text, "[USER PROFILE]", None)

        changed = False
        if new_mem is not None and new_mem.strip() != mem.strip():
            MEMORY_FILE.write_text(_MEMORY_HEADER + new_mem.strip() + "\n", encoding="utf-8")
            changed = True
        if new_user is not None and new_user.strip() != user.strip():
            USER_FILE.write_text(_USER_HEADER + new_user.strip() + "\n", encoding="utf-8")
            changed = True
        return changed
    except Exception:
        return False


def _extract(text: str, start_tag: str, end_tag: str | None) -> str | None:
    try:
        idx   = text.index(start_tag)
        start = idx + len(start_tag)
        if end_tag:
            idx2 = text.find(end_tag, start)
            return text[start:idx2].strip() if idx2 != -1 else text[start:].strip()
        return text[start:].strip()
    except ValueError:
        return None
