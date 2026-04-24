"""
Ollama provider — local models via OpenAI-compatible API.

Tool schemas expected in Anthropic format and converted to OpenAI format internally.
"""
import json
import os
from typing import Iterator

from .base import LLMProvider, LLMResponse, ToolCall, Usage, register
from .openrouter import OpenRouterProvider  # reuse conversion helpers

_BASE_URL = "http://localhost:11434/v1"


@register("ollama")
class OllamaProvider(LLMProvider):
    def __init__(self, model: str | None = None, temperature: float = 0.1, **_):
        self._model = model or os.getenv("OLLAMA_MODEL", "gemma3")
        self._temperature = temperature
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(base_url=_BASE_URL, api_key="ollama")
        return self._client

    @property
    def model_id(self) -> str:
        return self._model

    def complete(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
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

    def unload(self) -> None:
        """Ask Ollama to release the model from VRAM."""
        try:
            import requests
            requests.post(
                "http://localhost:11434/api/generate",
                json={"model": self._model, "keep_alive": 0},
                timeout=5,
            )
        except Exception:
            pass
