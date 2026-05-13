"""
OpenRouter LLM provider (https://openrouter.ai).

OpenRouter acts as a unified gateway to hundreds of models.  It accepts the
standard OpenAI chat-completion format and returns usage stats (including
per-token pricing when available).

Required env var:  OPENROUTER_API_KEY
Optional env vars: OPENROUTER_REFERER  (defaults to "https://github.com/majestic-agent/majestic")
                   OPENROUTER_TITLE    (defaults to "Majestic Agent")
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from .base import BaseLLM, LLMError

logger = logging.getLogger(__name__)

_BASE_URL = "https://openrouter.ai/api/v1"
_TIMEOUT = 120.0  # seconds
_DEFAULT_MAX_TOKENS = 4096  # prevent models with huge context windows from defaulting to max


class OpenRouterLLM(BaseLLM):
    """LLM provider backed by OpenRouter."""

    provider_name = "openrouter"

    def __init__(
        self,
        api_key: str | None = None,
        referer: str | None = None,
        title: str | None = None,
        timeout: float = _TIMEOUT,
    ) -> None:
        self._api_key: str = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self._referer: str = (
            referer
            or os.environ.get("OPENROUTER_REFERER", "https://github.com/majestic-agent/majestic")
        )
        self._title: str = title or os.environ.get("OPENROUTER_TITLE", "Majestic Agent")
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "HTTP-Referer": self._referer,
            "X-Title": self._title,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _parse_cost(response_json: dict, input_tokens: int, output_tokens: int) -> float:
        """
        Extract cost from the OpenRouter response if present, otherwise fall
        back to the rough estimate of $0.001 / 1 K tokens.
        """
        # OpenRouter may include usage.cost (in USD) directly.
        usage = response_json.get("usage", {})
        if isinstance(usage, dict) and "cost" in usage:
            try:
                return float(usage["cost"])
            except (TypeError, ValueError):
                pass
        return BaseLLM._estimate_cost(input_tokens, output_tokens)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[dict],
        model: str,
        **kwargs: Any,
    ) -> dict:
        """Send a chat request to OpenRouter and return a standardised dict."""
        if not self._api_key:
            raise LLMError("OPENROUTER_API_KEY is not set", provider=self.provider_name)

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": kwargs.pop("max_tokens", _DEFAULT_MAX_TOKENS),
            **kwargs,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                response = await client.post(
                    f"{_BASE_URL}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
            except httpx.TimeoutException as exc:
                raise LLMError(
                    f"Request timed out after {self._timeout}s: {exc}",
                    provider=self.provider_name,
                ) from exc
            except httpx.RequestError as exc:
                raise LLMError(
                    f"Network error: {exc}",
                    provider=self.provider_name,
                ) from exc

        if response.status_code != 200:
            body = response.text[:500]
            raise LLMError(
                f"HTTP {response.status_code}: {body}",
                provider=self.provider_name,
                status_code=response.status_code,
            )

        try:
            data = response.json()
        except Exception as exc:
            raise LLMError(
                f"Invalid JSON response: {exc}",
                provider=self.provider_name,
            ) from exc

        # Validate minimal structure
        try:
            content: str = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(
                f"Unexpected response structure: {exc} — body: {str(data)[:300]}",
                provider=self.provider_name,
            ) from exc

        usage = data.get("usage") or {}
        input_tokens: int = int(usage.get("prompt_tokens", 0))
        output_tokens: int = int(usage.get("completion_tokens", 0))
        cost: float = self._parse_cost(data, input_tokens, output_tokens)

        logger.debug(
            "OpenRouter chat | model=%s | in=%d out=%d cost=$%.6f",
            model,
            input_tokens,
            output_tokens,
            cost,
        )

        return {
            "content": content,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
        }

    async def is_available(self) -> bool:
        """
        Ping OpenRouter with a minimal request.

        Uses the models endpoint (no tokens consumed) to verify connectivity
        and API key validity.
        """
        if not self._api_key:
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{_BASE_URL}/models",
                    headers=self._headers(),
                )
            return response.status_code == 200
        except Exception as exc:  # noqa: BLE001
            logger.debug("OpenRouter is_available check failed: %s", exc)
            return False
