"""LLM call helpers — context-error detection, message shrinking, retry."""

from __future__ import annotations

import copy


def _is_context_error(exc: Exception) -> bool:
    s = str(exc).lower()
    return any(k in s for k in [
        "peer closed", "incomplete message", "context length", "too long",
        "maximum context", "context_length_exceeded", "413", "payload too large",
        "token", "input is too long",
    ])


def _shrink_messages(messages: list[dict], shrink_factor: float) -> list[dict]:
    """Keep corpus header + instructions, shrink the middle to fit token budget."""
    msgs = copy.deepcopy(messages)
    for m in msgs:
        if m["role"] != "user":
            continue
        content = m["content"]
        target = int(len(content) * shrink_factor)
        if len(content) <= target:
            continue
        head_end = max(200, len(content) // 10)
        tail_start = int(len(content) * 0.75)
        head = content[:head_end]
        tail = content[tail_start:]
        middle_budget = max(0, target - len(head) - len(tail) - 60)
        mid = content[head_end:tail_start]
        m["content"] = (
            head + mid[:middle_budget]
            + "\n[... corpus trimmed for token budget ...]\n"
            + tail
        )
    return msgs


async def llm_with_retry(
    llm,
    messages: list[dict],
    step_type: str = "reason",
    shrink_factor: float = 0.6,
    max_retries: int = 2,
) -> dict:
    """LLM call with automatic message shrinking on context-length errors."""
    current = messages
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await llm.chat(current, step_type=step_type)
        except Exception as exc:
            last_exc = exc
            if not _is_context_error(exc) or attempt >= max_retries:
                raise
            current = _shrink_messages(current, shrink_factor)
    raise last_exc  # type: ignore[misc]
