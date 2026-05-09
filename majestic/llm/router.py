"""
LLM Router — provider fallback chain with per-step model routing.

Priority order:  OpenRouter → Anthropic → OpenAI → raise LLMError

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

import logging
from typing import Any

from .base import BaseLLM, LLMError
from .openrouter import OpenRouterLLM
from .anthropic import AnthropicLLM
from .openai import OpenAILLM

logger = logging.getLogger(__name__)


class LLMRouter:
    """
    Routes LLM calls to the best available provider with automatic fallback.

    Provider priority:
        1. OpenRouter  — requires OPENROUTER_API_KEY
        2. Anthropic   — requires ANTHROPIC_API_KEY
        3. OpenAI      — requires OPENAI_API_KEY

    If a provider does not have a key configured it is skipped silently.
    If all configured providers fail, ``LLMError`` is raised.
    """

    def __init__(self, settings: Any) -> None:
        """
        Parameters
        ----------
        settings:
            A ``majestic.config.settings.Settings`` instance.  Used to read
            API keys (via ``settings.openrouter_api_key`` etc.) and model
            routing (via ``settings.get_model(step_type)``).
        """
        self._settings = settings
        self._providers: list[BaseLLM] = self._build_provider_list(settings)

        if not self._providers:
            raise LLMError(
                "No LLM providers are configured. "
                "Set at least one of: OPENROUTER_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY "
                f"in the '{settings.profile_name}' profile's .env file."
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
        providers: list[BaseLLM] = []

        if settings.openrouter_api_key:
            providers.append(OpenRouterLLM(api_key=settings.openrouter_api_key))

        if settings.anthropic_api_key:
            providers.append(AnthropicLLM(api_key=settings.anthropic_api_key))

        if settings.openai_api_key:
            providers.append(OpenAILLM(api_key=settings.openai_api_key))

        return providers

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

        for provider in self._providers:
            try:
                logger.debug(
                    "LLMRouter trying | provider=%s model=%s step_type=%s",
                    provider.provider_name,
                    model,
                    step_type,
                )
                result = await provider.chat(messages=messages, model=model, **kwargs)
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
            except LLMError as exc:
                logger.warning(
                    "LLMRouter provider failed | provider=%s error=%s",
                    provider.provider_name,
                    exc,
                )
                last_error = exc
                continue

        # All providers exhausted.
        providers_tried = [p.provider_name for p in self._providers]
        raise LLMError(
            f"All LLM providers failed for step_type='{step_type}' model='{model}'. "
            f"Providers tried: {providers_tried}. "
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
    def provider_names(self) -> list[str]:
        """Names of configured providers in priority order."""
        return [p.provider_name for p in self._providers]
