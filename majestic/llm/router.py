"""
LLM Router — provider fallback chain with per-step model routing.

Priority order:  OpenRouter → Anthropic → OpenAI → Ollama → raise LLMError

Ollama (local) is included automatically when OLLAMA_BASE_URL is set.
If no cloud keys are present and Ollama is configured, Ollama runs first.

The router is initialised once per agent session (in the runtime or gateway)
and reused for every LLM call.  It reads API keys from the profile's
``Settings`` object so that each profile can use different credentials.

Usage::

    from majestic.config.settings import Settings
    from majestic.llm.router import LLMRouter

    settings = Settings("default")
    router = LLMRouter(settings)

    result = await router.chat(
        messages=[{"role": "user", "content": "Hello!"}],
        step_type="simple",
    )
    # result → {"content": ..., "input_tokens": ..., "output_tokens": ...,
    #            "cost": ..., "model": ..., "provider": ...}
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .base import BaseLLM, LLMError
from .openrouter import OpenRouterLLM
from .anthropic import AnthropicLLM
from .openai import OpenAILLM
from .ollama import OllamaLLM

logger = logging.getLogger(__name__)


class LLMRouter:
    """
    Routes LLM calls to the best available provider with automatic fallback.

    Provider priority (cloud keys present):
        1. OpenRouter  — requires OPENROUTER_API_KEY
        2. Anthropic   — requires ANTHROPIC_API_KEY
        3. OpenAI      — requires OPENAI_API_KEY
        4. Ollama      — OLLAMA_BASE_URL set (local, appended as last resort)

    Local-only mode (no cloud keys):
        If only OLLAMA_BASE_URL is set, Ollama runs first.

    If a provider does not have a key/URL configured it is skipped silently.
    If all configured providers fail, ``LLMError`` is raised.
    """

    _CONTEXT_LIMITS: dict[str, int] = {
        "anthropic":  200_000,
        "openrouter": 128_000,
        "openai":     128_000,
        "ollama":       8_000,
    }

    def __init__(self, settings: Any) -> None:
        self._settings = settings
        self._providers: list[BaseLLM] = self._build_provider_list(settings)

        if not self._providers:
            raise LLMError(
                "No LLM providers are configured.\n"
                "Add OPENROUTER_API_KEY / ANTHROPIC_API_KEY / OPENAI_API_KEY to .env, "
                "or set OLLAMA_BASE_URL for local models.\n"
                "Run  majestic setup  for guided configuration."
            )

        logger.info(
            "LLMRouter initialised | providers=%s",
            [p.provider_name for p in self._providers],
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_provider_list(settings: Any) -> list[BaseLLM]:
        """Return providers in priority order, skipping unconfigured ones."""
        cloud: list[BaseLLM] = []
        local: list[BaseLLM] = []

        if settings.openrouter_api_key:
            cloud.append(OpenRouterLLM(api_key=settings.openrouter_api_key))

        if settings.anthropic_api_key:
            cloud.append(AnthropicLLM(api_key=settings.anthropic_api_key))

        if settings.openai_api_key:
            cloud.append(OpenAILLM(api_key=settings.openai_api_key))

        if settings.ollama_base_url:
            local.append(OllamaLLM(
                base_url=settings.ollama_base_url,
                default_model=settings.ollama_model,
            ))

        # If only Ollama is configured, put it first; otherwise append after cloud
        if not cloud and local:
            return local
        return cloud + local

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[dict],
        step_type: str = "reason",
        **kwargs: Any,
    ) -> dict:
        """
        Send a chat request using the appropriate model for *step_type*.

        Parameters
        ----------
        messages:
            OpenAI-style message list (system / user / assistant).
        step_type:
            Logical step label: "reason", "simple", "code", "reflection", or
            any key defined in the profile's ``model_routing`` section.
            Controls which model is selected via ``settings.get_model()``.
        **kwargs:
            Extra parameters forwarded to the provider (temperature,
            max_tokens, …).

        Returns
        -------
        dict with keys:
            content        (str)   – Assistant reply text.
            input_tokens   (int)   – Prompt token count.
            output_tokens  (int)   – Completion token count.
            cost           (float) – Estimated USD cost.
            model          (str)   – Model identifier that was used.
            provider       (str)   – Provider name that succeeded.

        Raises
        ------
        LLMError
            If all configured providers fail.
        """
        model: str = self._settings.get_model(step_type)
        last_error: LLMError | None = None

        for attempt, provider in enumerate(self._providers):
            try:
                logger.debug(
                    "LLMRouter trying | provider=%s model=%s step_type=%s",
                    provider.provider_name,
                    model,
                    step_type,
                )
                provider_kwargs = dict(kwargs)
                # Enable prompt caching for stable system prompts on Anthropic
                if step_type in ("reason", "reflection") and provider.provider_name == "anthropic":
                    provider_kwargs.setdefault("use_cache", True)
                # tools kwarg is forwarded as-is; providers convert to their own format
                result = await provider.chat(messages=messages, model=model, **provider_kwargs)
                result["model"] = model
                result["provider"] = provider.provider_name
                logger.debug(
                    "LLMRouter success | provider=%s model=%s in=%d out=%d cost=$%.6f",
                    provider.provider_name,
                    model,
                    result["input_tokens"],
                    result["output_tokens"],
                    result["cost"],
                )
                return result
            except asyncio.TimeoutError:
                logger.warning(
                    "LLMRouter timeout | provider=%s — moving to next",
                    provider.provider_name,
                )
                last_error = LLMError("Request timed out", provider=provider.provider_name)
                # No backoff on timeout — move to next provider immediately
                continue
            except LLMError as exc:
                logger.warning(
                    "LLMRouter provider failed | provider=%s error=%s",
                    provider.provider_name,
                    exc,
                )
                last_error = exc
                # Exponential backoff before trying next provider
                if attempt + 1 < len(self._providers):
                    delay = min(2 ** attempt, 8)
                    await asyncio.sleep(delay)
                continue

        # All providers exhausted.
        providers_tried = [p.provider_name for p in self._providers]
        raise LLMError(
            f"All LLM providers failed for step_type='{step_type}' model='{model}'. "
            f"Providers tried: {providers_tried}. "
            f"Last error: {last_error}"
        )

    async def stream(
        self,
        messages: list[dict],
        step_type: str = "reason",
        **kwargs: Any,
    ):
        """
        Stream text tokens from the best available provider.

        Tries providers in priority order.  Falls back to the next provider
        only if the current one raises before yielding any tokens.
        """
        model: str = self._settings.get_model(step_type)

        # Enable prompt caching for Anthropic on stable prompts
        if step_type in ("reason", "reflection"):
            kwargs.setdefault("use_cache", True)

        last_error: LLMError | None = None

        for provider in self._providers:
            buffer: list[str] = []
            try:
                async for token in provider.stream(messages=messages, model=model, **kwargs):
                    buffer.append(token)
                    yield token
                return  # provider succeeded
            except LLMError as exc:
                if buffer:
                    # Already started streaming — cannot fallback, propagate
                    raise
                logger.warning(
                    "LLMRouter stream: provider %s failed before first token: %s",
                    provider.provider_name,
                    exc,
                )
                last_error = exc
                continue

        raise LLMError(
            f"All LLM providers failed during streaming for step_type='{step_type}'. "
            f"Last error: {last_error}"
        )

    async def is_any_available(self) -> bool:
        """
        Return True if at least one configured provider is reachable.

        Checks providers in priority order and returns on the first success.
        Useful for startup health-checks.
        """
        for provider in self._providers:
            try:
                if await provider.is_available():
                    logger.debug("Provider available: %s", provider.provider_name)
                    return True
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "Provider availability check raised: %s — %s",
                    provider.provider_name,
                    exc,
                )
        return False

    @property
    def context_limit(self) -> int:
        """Context window size (tokens) for the primary provider."""
        if self._providers:
            return self._CONTEXT_LIMITS.get(self._providers[0].provider_name, 128_000)
        return 128_000

    @property
    def provider_names(self) -> list[str]:
        """Names of configured providers in priority order."""
        return [p.provider_name for p in self._providers]
