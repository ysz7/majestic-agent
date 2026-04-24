"""
Anthropic provider — direct SDK, no langchain dependency.
"""
import os
from typing import Iterator

from .base import LLMProvider, LLMResponse, Usage, register

_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-7":           (15.0, 75.0),
    "claude-sonnet-4-6":         (3.0,  15.0),
    "claude-haiku-4-5-20251001": (0.8,   4.0),
    "claude-haiku-4-5":          (0.8,   4.0),
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
        in_price, out_price = _PRICING.get(self._model, (3.0, 15.0))
        return (usage.input_tokens * in_price + usage.output_tokens * out_price) / 1_000_000

    def complete(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 4096,
    ) -> LLMResponse:
        client = self._get_client()
        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": self._temperature,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        msg = client.messages.create(**kwargs)
        usage = Usage(
            input_tokens=msg.usage.input_tokens,
            output_tokens=msg.usage.output_tokens,
            cache_read_tokens=getattr(msg.usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(msg.usage, "cache_creation_input_tokens", 0) or 0,
        )
        return LLMResponse(
            content=msg.content[0].text if msg.content else "",
            usage=usage,
            finish_reason=msg.stop_reason or "stop",
            model=msg.model,
        )

    def stream(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 4096,
    ) -> Iterator[str]:
        client = self._get_client()
        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": self._temperature,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        with client.messages.stream(**kwargs) as s:
            yield from s.text_stream
