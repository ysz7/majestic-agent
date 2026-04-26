"""
Anthropic provider — direct SDK, no langchain dependency.

Messages normalized format → Anthropic native format via _convert_messages().
Tool schemas expected in Anthropic format: {name, description, input_schema}.
"""
import os
from typing import Iterator

from .base import LLMProvider, LLMResponse, ToolCall, Usage, register

# (input, output, cache_write_multiplier, cache_read_multiplier)
_PRICING: dict[str, tuple[float, float, float, float]] = {
    "claude-opus-4-7":           (15.0, 75.0, 1.25, 0.10),
    "claude-sonnet-4-6":         (3.0,  15.0, 1.25, 0.10),
    "claude-haiku-4-5-20251001": (0.8,   4.0, 1.25, 0.10),
    "claude-haiku-4-5":          (0.8,   4.0, 1.25, 0.10),
}


@register("anthropic")
class AnthropicProvider(LLMProvider):
    def __init__(self, model: str | None = None, temperature: float = 0.1, **_):
        self._model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        self._temperature = temperature
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    @property
    def model_id(self) -> str:
        return self._model

    def estimated_cost(self, usage: Usage) -> float:
        in_p, out_p, cw_m, cr_m = _PRICING.get(self._model, (3.0, 15.0, 1.25, 0.10))
        return (
            usage.input_tokens       * in_p +
            usage.output_tokens      * out_p +
            usage.cache_write_tokens * in_p * cw_m +
            usage.cache_read_tokens  * in_p * cr_m
        ) / 1_000_000

    def _convert_messages(self, messages: list[dict]) -> list[dict]:
        """Convert normalized messages to Anthropic native format."""
        result: list[dict] = []
        i = 0
        while i < len(messages):
            m = messages[i]
            role = m["role"]

            if role == "tool_result":
                # Merge consecutive tool_result messages into one user message
                blocks = []
                while i < len(messages) and messages[i]["role"] == "tool_result":
                    blocks.append({
                        "type":        "tool_result",
                        "tool_use_id": messages[i]["tool_call_id"],
                        "content":     str(messages[i]["content"]),
                    })
                    i += 1
                result.append({"role": "user", "content": blocks})
                continue

            elif role == "assistant" and m.get("tool_calls"):
                blocks: list[dict] = []
                if m.get("content"):
                    blocks.append({"type": "text", "text": m["content"]})
                for tc in m["tool_calls"]:
                    blocks.append({
                        "type":  "tool_use",
                        "id":    tc["id"],
                        "name":  tc["name"],
                        "input": tc["arguments"],
                    })
                result.append({"role": "assistant", "content": blocks})

            elif role in ("user", "assistant"):
                result.append({"role": role, "content": m["content"]})

            i += 1
        return result

    def complete(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        client = self._get_client()
        kwargs: dict = {
            "model":       self._model,
            "max_tokens":  max_tokens,
            "temperature": self._temperature,
            "messages":    self._convert_messages(messages),
        }
        # Prompt caching — system prompt and tool schemas are static per session,
        # marking them ephemeral lets Anthropic cache them (~10x cheaper on reads).
        if system:
            kwargs["system"] = [{"type": "text", "text": system,
                                  "cache_control": {"type": "ephemeral"}}]
        if tools:
            cached = list(tools)
            cached[-1] = {**cached[-1], "cache_control": {"type": "ephemeral"}}
            kwargs["tools"] = cached

        msg = client.messages.create(**kwargs)

        text_content = ""
        tool_calls: list[ToolCall] = []
        for block in msg.content:
            if block.type == "text":
                text_content += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input,
                ))

        usage = Usage(
            input_tokens=msg.usage.input_tokens,
            output_tokens=msg.usage.output_tokens,
            cache_read_tokens=getattr(msg.usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(msg.usage, "cache_creation_input_tokens", 0) or 0,
        )
        return LLMResponse(
            content=text_content,
            usage=usage,
            finish_reason=msg.stop_reason or "stop",
            model=msg.model,
            tool_calls=tool_calls,
        )

    def stream(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 4096,
    ) -> Iterator[str]:
        client = self._get_client()
        kwargs: dict = {
            "model":       self._model,
            "max_tokens":  max_tokens,
            "temperature": self._temperature,
            "messages":    self._convert_messages(messages),
        }
        if system:
            kwargs["system"] = system
        with client.messages.stream(**kwargs) as s:
            yield from s.text_stream
