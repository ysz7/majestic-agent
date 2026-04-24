"""
OpenRouter provider — 200+ models via OpenAI-compatible API.

Tool schemas expected in Anthropic format and converted to OpenAI format internally.
"""
import json
import os
from typing import Iterator

from .base import LLMProvider, LLMResponse, ToolCall, Usage, register

_BASE_URL = "https://openrouter.ai/api/v1"
_DEFAULT_MODEL = "google/gemini-flash-1.5"


@register("openrouter")
class OpenRouterProvider(LLMProvider):
    def __init__(self, model: str | None = None, temperature: float = 0.1, **_):
        self._model = model or os.getenv("OPENROUTER_MODEL", _DEFAULT_MODEL)
        self._temperature = temperature
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(
                base_url=_BASE_URL,
                api_key=os.getenv("OPENROUTER_API_KEY", ""),
            )
        return self._client

    @property
    def model_id(self) -> str:
        return self._model

    @staticmethod
    def _convert_tools(tools: list[dict]) -> list[dict]:
        """Anthropic format → OpenAI function-calling format."""
        return [
            {
                "type": "function",
                "function": {
                    "name":        t["name"],
                    "description": t.get("description", ""),
                    "parameters":  t.get("input_schema", {"type": "object", "properties": {}}),
                },
            }
            for t in tools
        ]

    @staticmethod
    def _convert_messages(messages: list[dict]) -> list[dict]:
        """Normalized format → OpenAI messages format."""
        result = []
        for m in messages:
            role = m["role"]
            if role == "tool_result":
                result.append({
                    "role":         "tool",
                    "tool_call_id": m["tool_call_id"],
                    "content":      str(m["content"]),
                })
            elif role == "assistant" and m.get("tool_calls"):
                oai_calls = []
                for tc in m["tool_calls"]:
                    oai_calls.append({
                        "id":   tc["id"],
                        "type": "function",
                        "function": {
                            "name":      tc["name"],
                            "arguments": json.dumps(tc["arguments"]),
                        },
                    })
                result.append({
                    "role":       "assistant",
                    "content":    m.get("content") or None,
                    "tool_calls": oai_calls,
                })
            else:
                result.append({"role": role, "content": m["content"]})
        return result

    def complete(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        client = self._get_client()
        converted = self._convert_messages(messages)
        msgs = ([{"role": "system", "content": system}] if system else []) + converted
        kwargs: dict = {
            "model":       self._model,
            "messages":    msgs,
            "max_tokens":  max_tokens,
            "temperature": self._temperature,
        }
        if tools:
            kwargs["tools"] = self._convert_tools(tools)
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
        converted = self._convert_messages(messages)
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
