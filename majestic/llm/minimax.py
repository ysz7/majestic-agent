"""
MiniMax provider — OpenAI-compatible API.

Requires MINIMAX_API_KEY and MINIMAX_GROUP_ID in .env.
"""
import os
from typing import Iterator

from .base import LLMProvider, LLMResponse, ToolCall, Usage, register
from .openrouter import OpenRouterProvider

_BASE_URL = "https://api.minimax.chat/v1"

_PRICING: dict[str, tuple[float, float]] = {
    "MiniMax-Text-01": (0.7, 2.1),
    "abab6.5s-chat":   (0.14, 0.42),
    "abab6.5g-chat":   (0.5, 1.5),
}


@register("minimax")
class MiniMaxProvider(LLMProvider):
    def __init__(self, model: str | None = None, temperature: float = 0.1, **_):
        self._model = model or os.getenv("MINIMAX_MODEL", "MiniMax-Text-01")
        self._temperature = temperature
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            api_key   = os.getenv("MINIMAX_API_KEY", "")
            group_id  = os.getenv("MINIMAX_GROUP_ID", "")
            base_url  = f"{_BASE_URL}?GroupId={group_id}" if group_id else _BASE_URL
            self._client = OpenAI(base_url=base_url, api_key=api_key)
        return self._client

    @property
    def model_id(self) -> str:
        return self._model

    def estimated_cost(self, usage: Usage) -> float:
        in_p, out_p = _PRICING.get(self._model, (1.0, 3.0))
        return (usage.input_tokens * in_p + usage.output_tokens * out_p) / 1_000_000

    def complete(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        import json
        client = self._get_client()
        converted = OpenRouterProvider._convert_messages(messages)
        msgs = ([{"role": "system", "content": system}] if system else []) + converted
        kwargs: dict = {
            "model":       self._model,
            "messages":    msgs,
            "max_tokens":  max_tokens,
            "temperature": self._temperature,
        }
        if tools:
            kwargs["tools"] = OpenRouterProvider._convert_tools(tools)
            kwargs["tool_choice"] = "auto"

        resp = client.chat.completions.create(**kwargs)
        u = resp.usage
        usage = Usage(
            input_tokens=getattr(u, "prompt_tokens", 0) or 0,
            output_tokens=getattr(u, "completion_tokens", 0) or 0,
        )
        choice = resp.choices[0] if resp.choices else None
        content = ""
        tool_calls: list[ToolCall] = []
        if choice:
            content = choice.message.content or ""
            for tc in getattr(choice.message, "tool_calls", None) or []:
                try:
                    args = json.loads(tc.function.arguments)
                except Exception:
                    args = {}
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

        return LLMResponse(
            content=content,
            usage=usage,
            finish_reason=(choice.finish_reason or "stop") if choice else "stop",
            model=self._model,
            tool_calls=tool_calls,
        )

    def stream(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 4096,
    ) -> Iterator[str]:
        client = self._get_client()
        converted = OpenRouterProvider._convert_messages(messages)
        msgs = ([{"role": "system", "content": system}] if system else []) + converted
        stream = client.chat.completions.create(
            model=self._model,
            messages=msgs,
            max_tokens=max_tokens,
            temperature=self._temperature,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content
