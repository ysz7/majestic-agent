"""
majestic.llm — LLM provider abstractions and router.

Public exports:
    BaseLLM       — abstract provider base class
    LLMError      — exception raised on provider failure
    OpenRouterLLM — OpenRouter provider
    AnthropicLLM  — Anthropic provider
    OpenAILLM     — OpenAI provider
    LLMRouter     — provider fallback chain with per-step model routing
"""

from .base import BaseLLM, LLMError
from .openrouter import OpenRouterLLM
from .anthropic import AnthropicLLM
from .openai import OpenAILLM
from .router import LLMRouter

__all__ = [
    "BaseLLM",
    "LLMError",
    "OpenRouterLLM",
    "AnthropicLLM",
    "OpenAILLM",
    "LLMRouter",
]
