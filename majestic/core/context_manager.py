import json


class ContextManager:
    MAX_TOOL_OUTPUT = 2000
    KEEP_RECENT_STEPS = 5

    def __init__(self, llm_router=None, max_tokens: int = 100000):
        self.llm = llm_router
        self.max_tokens = max_tokens

    def compact(self, messages: list[dict]) -> list[dict]:
        """
        Step 1 (free, rule-based):
        - Truncate long tool outputs
        - Collapse old assistant/tool messages into a summary
        - Deduplicate RAG chunks

        Step 2 (LLM, last resort):
        - If still too long, summarize with simple model
        """
        messages = self._truncate_long_outputs(messages)
        messages = self._collapse_old_steps(messages)

        if self._estimate_tokens(messages) > self.max_tokens and self.llm:
            messages = self._llm_compact(messages)

        return messages

    def _truncate_long_outputs(self, messages: list[dict]) -> list[dict]:
        result = []
        for msg in messages:
            if msg["role"] == "user" and msg["content"].startswith("Tool result"):
                content = msg["content"]
                if len(content) > self.MAX_TOOL_OUTPUT:
                    content = content[:self.MAX_TOOL_OUTPUT] + "\n... [truncated]"
                result.append({**msg, "content": content})
            else:
                result.append(msg)
        return result

    def _collapse_old_steps(self, messages: list[dict]) -> list[dict]:
        # Keep system messages + last N tool exchanges + current user message
        system_msgs = [m for m in messages if m["role"] == "system"]
        non_system = [m for m in messages if m["role"] != "system"]

        if len(non_system) <= self.KEEP_RECENT_STEPS * 2 + 1:
            return messages

        # Keep first (original task) and last KEEP_RECENT_STEPS*2 messages
        first_user = non_system[:1]
        recent = non_system[-(self.KEEP_RECENT_STEPS * 2):]
        omitted = len(non_system) - 1 - len(recent)

        summary_msg = {"role": "user", "content": f"[{omitted} earlier steps omitted for brevity]"}

        return system_msgs + first_user + [summary_msg] + recent

    def _estimate_tokens(self, messages: list[dict]) -> int:
        total = sum(len(m.get("content", "")) for m in messages)
        return total // 4  # rough chars-to-tokens ratio

    def _llm_compact(self, messages: list[dict]) -> list[dict]:
        # Placeholder: in real use would call self.llm.chat() synchronously
        # For now just do aggressive truncation
        return self._collapse_old_steps(messages)
