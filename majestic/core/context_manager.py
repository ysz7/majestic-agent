import logging

logger = logging.getLogger(__name__)


class ContextManager:
    MAX_TOOL_OUTPUT = 2000
    KEEP_RECENT_STEPS = 5
    COMPRESS_THRESHOLD = 0.80  # trigger when > 80% of model context limit used

    def __init__(self, llm_router=None, max_tokens: int = 100_000):
        self.llm = llm_router
        self.max_tokens = max_tokens

    # ------------------------------------------------------------------
    # Public async entrypoint — call once per ReAct iteration
    # ------------------------------------------------------------------

    async def compress_if_needed(
        self, messages: list[dict], model_limit: int | None = None
    ) -> list[dict]:
        """
        Compress messages if estimated token count exceeds COMPRESS_THRESHOLD
        of the model's context limit.

        Strategy:
          1. Rule-based (free): truncate long tool outputs, collapse old steps
          2. LLM summarization (last resort): summarize the middle of the
             conversation, keeping system prompt + first user message + last 6
             messages (anchor) untouched.
        """
        limit = model_limit or self.max_tokens
        if self._estimate_tokens(messages) < limit * self.COMPRESS_THRESHOLD:
            return messages

        messages = self._truncate_long_outputs(messages)
        messages = self._collapse_old_steps(messages)

        if self._estimate_tokens(messages) >= limit * self.COMPRESS_THRESHOLD and self.llm:
            messages = await self._llm_compact(messages)

        return messages

    # ------------------------------------------------------------------
    # Rule-based compaction (sync, free)
    # ------------------------------------------------------------------

    def compact(self, messages: list[dict]) -> list[dict]:
        """Synchronous rule-based compaction (used by callers that can't await)."""
        messages = self._truncate_long_outputs(messages)
        messages = self._collapse_old_steps(messages)
        return messages

    def _truncate_long_outputs(self, messages: list[dict]) -> list[dict]:
        result = []
        for msg in messages:
            if msg["role"] == "user" and msg["content"].startswith("Tool result"):
                content = msg["content"]
                if len(content) > self.MAX_TOOL_OUTPUT:
                    content = content[: self.MAX_TOOL_OUTPUT] + "\n... [truncated]"
                result.append({**msg, "content": content})
            else:
                result.append(msg)
        return result

    def _collapse_old_steps(self, messages: list[dict]) -> list[dict]:
        system_msgs = [m for m in messages if m["role"] == "system"]
        non_system  = [m for m in messages if m["role"] != "system"]

        if len(non_system) <= self.KEEP_RECENT_STEPS * 2 + 1:
            return messages

        first_user = non_system[:1]
        recent     = non_system[-(self.KEEP_RECENT_STEPS * 2):]
        omitted    = len(non_system) - 1 - len(recent)

        summary_msg = {
            "role": "user",
            "content": f"[{omitted} earlier steps omitted for brevity]",
        }
        return system_msgs + first_user + [summary_msg] + recent

    def _estimate_tokens(self, messages: list[dict]) -> int:
        total = sum(len(m.get("content", "")) for m in messages)
        return total // 4

    # ------------------------------------------------------------------
    # LLM-based compaction (async, last resort)
    # ------------------------------------------------------------------

    async def _llm_compact(self, messages: list[dict]) -> list[dict]:
        """
        Anchored iterative summarization:
          - Keep: system prompt + first user message + last 6 messages
          - Summarize: everything in between with one LLM call (step_type=simple)
        """
        system_msgs = [m for m in messages if m["role"] == "system"]
        non_system  = [m for m in messages if m["role"] != "system"]

        ANCHOR = 6
        if len(non_system) <= ANCHOR + 1:
            return messages

        first  = non_system[:1]
        middle = non_system[1 : len(non_system) - ANCHOR]
        anchor = non_system[len(non_system) - ANCHOR :]

        if not middle:
            return messages

        turns = "\n".join(
            f"[{m['role'].upper()}]: {str(m.get('content', ''))[:300]}"
            for m in middle
        )
        prompt = (
            "Summarize the following conversation turns as a single compact paragraph. "
            "Preserve key facts, tool calls made, and their results. Be concise.\n\n"
            + turns
        )
        try:
            resp = await self.llm.chat(
                [{"role": "user", "content": prompt}],
                step_type="simple",
            )
            summary = resp.get("content", "").strip()
            n = len(middle)
            compressed = {
                "role": "user",
                "content": f"[COMPRESSED: {n} turns summarized]\n{summary}",
            }
            logger.info("ContextManager: compressed %d messages into summary", n)
            return system_msgs + first + [compressed] + anchor
        except Exception as exc:
            logger.warning("ContextManager: LLM summarization failed, keeping truncated: %s", exc)
            return messages
