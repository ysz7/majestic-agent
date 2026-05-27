"""
Base abstractions for LLM providers.
"""

from __future__ import annotations

from typing import AsyncGenerator


class LLMError(Exception):
    """Raised when an LLM provider call fails and all fallbacks are exhausted."""

    def __init__(self, message: str, provider: str | None = None, status_code: int | None = None) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code

    def __str__(self) -> str:
        parts = [super().__str__()]
        if self.provider:
            parts.append(f"provider={self.provider}")
        if self.status_code is not None:
            parts.append(f"status={self.status_code}")
        return " | ".join(parts)


class BaseLLM:
    """
    Abstract base class that every LLM provider must implement.

    All methods are async. The ``chat`` method must return a standardised
    response dict so that higher-level code never needs to inspect which
    provider is currently in use.
    """

    # Subclasses should set these for logging / debugging.
    provider_name: str = "base"

    async def chat(
        self,
        messages: list[dict],
        model: str,
        **kwargs,
    ) -> dict:
        """
        Send a chat completion request.

        Parameters
        ----------
        messages:
            List of message dicts in OpenAI-style format:
            ``[{"role": "system"|"user"|"assistant", "content": "..."}]``.
        model:
            Model identifier string (provider-specific).
        **kwargs:
            Extra parameters forwarded to the provider (temperature, max_tokens, …).

        Returns
        -------
        dict with keys:
            content        (str)   – The assistant's reply text.
            input_tokens   (int)   – Number of prompt tokens consumed.
            output_tokens  (int)   – Number of completion tokens generated.
            cost           (float) – Estimated cost in USD.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement `chat()`"
        )

    async def stream(
        self,
        messages: list[dict],
        model: str,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """
        Yield text tokens as they arrive from the LLM.

        Default implementation falls back to a single non-streaming chat() call
        and yields the full content as one chunk.  Override in subclasses to
        enable true token-by-token streaming.
        """
        response = await self.chat(messages=messages, model=model, **kwargs)
        content = response.get("content", "")
        if content:
            yield content

    async def is_available(self) -> bool:
        """
        Probe the provider to check whether it is reachable and the API key
        is valid.  Should never raise — return False on any error.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement `is_available()`"
        )

    # ------------------------------------------------------------------
    # Helpers shared across providers
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_cost(input_tokens: int, output_tokens: int, cost_per_1k: float = 0.001) -> float:
        """
        Return a rough USD cost estimate when the provider does not supply
        pricing in its response.

        Default rate: $0.001 per 1 000 tokens (blended).
        """
        total_tokens = input_tokens + output_tokens
        return round(total_tokens / 1_000 * cost_per_1k, 8)
