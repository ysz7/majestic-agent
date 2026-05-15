"""
Anthropic LLM provider (https://api.anthropic.com).

Sends requests to the Anthropic Messages API using httpx (no SDK dependency).
Converts OpenAI-style message lists to Anthropic format automatically:
  - "system" role messages are extracted and merged into the top-level
    ``system`` field.
  - "user" / "assistant" role messages are passed as-is in ``messages``.

Required env var: ANTHROPIC_API_KEY
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from .base import BaseLLM, LLMError

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.anthropic.com/v1"
_API_VERSION = "2023-06-01"
_TIMEOUT = 120.0  # seconds
_DEFAULT_MAX_TOKENS = 4096


class AnthropicLLM(BaseLLM):
    """LLM provider backed by the Anthropic Messages API."""

    provider_name = "anthropic"

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = _TIMEOUT,
    ) -> None:
        self._api_key: str = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self, cache: bool = False) -> dict[str, str]:
        h = {
            "x-api-key": self._api_key,
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
        }
        if cache:
            h["anthropic-beta"] = "prompt-caching-2024-07-31"
        return h

    @staticmethod
    def _convert_messages(messages: list[dict]) -> tuple[str, list[dict]]:
        """
        Split an OpenAI-style message list into:
          - system_prompt (str): merged text of all "system" messages.
          - messages (list[dict]): remaining "user" / "assistant" turns.

        Anthropic requires:
          1. The ``system`` parameter to be a plain string (not a message).
          2. The ``messages`` list to start with a "user" turn.
          3. Alternating user / assistant turns (no consecutive same roles).
        """
        system_parts: list[str] = []
        converted: list[dict] = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                if content:
                    system_parts.append(content)
            elif role in ("user", "assistant"):
                converted.append({"role": role, "content": content})
            # Ignore unknown roles silently.

        system_prompt = "\n\n".join(system_parts)
        return system_prompt, converted

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[dict],
        model: str,
        **kwargs: Any,
    ) -> dict:
        """Send a chat request to the Anthropic Messages API."""
        if not self._api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set", provider=self.provider_name)

        use_cache: bool = kwargs.pop("use_cache", False)

        system_prompt, converted_messages = self._convert_messages(messages)

        if not converted_messages:
            raise LLMError(
                "No user/assistant messages found after conversion",
                provider=self.provider_name,
            )

        # Ensure the conversation starts with a user turn.
        if converted_messages[0]["role"] != "user":
            raise LLMError(
                "Anthropic requires the first message to have role='user'",
                provider=self.provider_name,
            )

        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": kwargs.pop("max_tokens", _DEFAULT_MAX_TOKENS),
            "messages": converted_messages,
        }
        if system_prompt:
            if use_cache:
                # Cache the system prompt — stable prefix, rarely changes
                payload["system"] = [
                    {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
                ]
            else:
                payload["system"] = system_prompt
        payload.update(kwargs)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                response = await client.post(
                    f"{_BASE_URL}/messages",
                    headers=self._headers(cache=use_cache),
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

        # Extract text content from Anthropic's content blocks.
        try:
            content_blocks: list[dict] = data["content"]
            text_parts = [
                block["text"]
                for block in content_blocks
                if block.get("type") == "text"
            ]
            content = "\n".join(text_parts)
        except (KeyError, TypeError) as exc:
            raise LLMError(
                f"Unexpected response structure: {exc} — body: {str(data)[:300]}",
                provider=self.provider_name,
            ) from exc

        usage = data.get("usage") or {}
        input_tokens: int = int(usage.get("input_tokens", 0))
        output_tokens: int = int(usage.get("output_tokens", 0))
        cost: float = self._estimate_cost(input_tokens, output_tokens)

        logger.debug(
            "Anthropic chat | model=%s | in=%d out=%d cost=$%.6f",
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
        Probe the Anthropic API.

        Uses the models list endpoint (GET /v1/models, introduced in
        anthropic-version 2023-06-01) which consumes no tokens.
        Falls back gracefully — never raises.
        """
        if not self._api_key:
            return False

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{_BASE_URL}/models",
                    headers=self._headers(),
                )
            # 200 → available.  401/403 → bad key (not available).
            return response.status_code == 200
        except Exception as exc:  # noqa: BLE001
            logger.debug("Anthropic is_available check failed: %s", exc)
            return False
