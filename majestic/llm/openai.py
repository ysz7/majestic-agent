"""
OpenAI provider — direct OpenAI API via OpenAI-compatible SDK.

Reuses OpenRouterProvider message/tool conversion (same format).
"""
import os

from .base import register
from .openrouter import OpenRouterProvider

_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_MODEL = "gpt-4o"

_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o":          (2.50, 10.00),
    "gpt-4o-mini":     (0.15,  0.60),
    "gpt-4-turbo":     (10.0, 30.00),
    "o1":              (15.0, 60.00),
    "o1-mini":         (3.00, 12.00),
    "o3-mini":         (1.10,  4.40),
}


@register("openai")
class OpenAIProvider(OpenRouterProvider):
    """OpenAI direct provider — same interface as OpenRouter, different endpoint."""

    def __init__(self, model: str | None = None, temperature: float = 0.1, **_):
        self._model = model or os.getenv("OPENAI_MODEL", _DEFAULT_MODEL)
        self._temperature = temperature
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(
                base_url=_BASE_URL,
                api_key=os.getenv("OPENAI_API_KEY", ""),
            )
        return self._client

    def estimated_cost(self, usage) -> float:
        in_price, out_price = _PRICING.get(self._model, (2.50, 10.00))
        return (usage.input_tokens * in_price + usage.output_tokens * out_price) / 1_000_000
