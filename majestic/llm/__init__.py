"""
majestic/llm — Multi-provider LLM abstraction.

Usage:
    from majestic.llm import get_provider
    provider = get_provider()           # creates from config/env
    resp = provider.complete([{"role": "user", "content": "hello"}])
"""
import os

from .base import LLMProvider, LLMResponse, Usage, get_provider as _get_provider

# Register all built-in providers (side-effect imports)
from . import anthropic, openai, openrouter, ollama  # noqa: F401

__all__ = ["LLMProvider", "LLMResponse", "Usage", "get_provider"]


def get_provider(model: str | None = None) -> LLMProvider:
    """Create an LLMProvider from current config/env."""
    try:
        from majestic.config import get as cfg_get
        name = cfg_get("llm.provider") or os.getenv("LLM_PROVIDER", "ollama")
        if model is None:
            model = cfg_get("llm.model") or None
    except Exception:
        name = os.getenv("LLM_PROVIDER", "ollama")
    name = (name or "ollama").lower()
    return _get_provider(name, model=model)
