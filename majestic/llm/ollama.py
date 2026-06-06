"""
Ollama LLM provider — local models via Ollama (https://ollama.com).

Ollama exposes an OpenAI-compatible API at http://localhost:11434/v1.
No API key required — just run `ollama serve` and pull a model.

Env vars:
    OLLAMA_BASE_URL  — defaults to http://localhost:11434
    OLLAMA_MODEL     — default model when no routing is specified (e.g. "llama3.2")
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from .base import BaseLLM, LLMError

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://localhost:11434"
_TIMEOUT = 120.0


class OllamaLLM(BaseLLM):
    """LLM provider backed by a local Ollama instance."""

    provider_name = "ollama"

    def __init__(
        self,
        base_url: str | None = None,
        default_model: str | None = None,
        timeout: float = _TIMEOUT,
    ) -> None:
        self._base_url = (base_url or os.environ.get("OLLAMA_BASE_URL", _DEFAULT_BASE_URL)).rstrip("/")
        self._default_model = default_model or os.environ.get("OLLAMA_MODEL", "llama3.2")
        self._timeout = timeout

    def _chat_url(self) -> str:
        return f"{self._base_url}/v1/chat/completions"

    def _tags_url(self) -> str:
        return f"{self._base_url}/api/tags"

    async def chat(self, messages: list[dict], model: str, **kwargs: Any) -> dict:
        """Send a chat request to the local Ollama instance."""
        effective_model = model or self._default_model

        # Drop kwargs that other providers understand but Ollama does not, so a
        # fallback to Ollama (with native-tool/cache kwargs set upstream) is safe.
        kwargs.pop("tools", None)
        kwargs.pop("use_cache", None)

        payload: dict[str, Any] = {
            "model": effective_model,
            "messages": messages,
            "stream": False,
            **kwargs,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                response = await client.post(self._chat_url(), json=payload)
            except httpx.ConnectError as exc:
                raise LLMError(
                    f"Cannot connect to Ollama at {self._base_url}. "
                    "Is `ollama serve` running?",
                    provider=self.provider_name,
                ) from exc
            except httpx.TimeoutException as exc:
                raise LLMError(
                    f"Ollama request timed out after {self._timeout}s",
                    provider=self.provider_name,
                ) from exc
            except httpx.RequestError as exc:
                raise LLMError(f"Ollama network error: {exc}", provider=self.provider_name) from exc

        if response.status_code != 200:
            raise LLMError(
                f"Ollama HTTP {response.status_code}: {response.text[:300]}",
                provider=self.provider_name,
                status_code=response.status_code,
            )

        try:
            data = response.json()
            content: str = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMError(
                f"Unexpected Ollama response: {exc} — body: {str(data)[:200]}",
                provider=self.provider_name,
            ) from exc

        usage = data.get("usage") or {}
        input_tokens: int = int(usage.get("prompt_tokens", 0))
        output_tokens: int = int(usage.get("completion_tokens", 0))

        logger.debug(
            "Ollama chat | model=%s | in=%d out=%d",
            effective_model,
            input_tokens,
            output_tokens,
        )

        return {
            "content": content,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": 0.0,  # local model — no cost
        }

    async def is_available(self) -> bool:
        """Check if Ollama is running and has at least one model."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(self._tags_url())
            if response.status_code != 200:
                return False
            data = response.json()
            return bool(data.get("models"))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Ollama is_available check failed: %s", exc)
            return False
