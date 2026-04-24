"""
LangChain compatibility shim.

Wraps LLMProvider to expose a .invoke(messages) interface compatible with
the existing core/ code that uses langchain-style llm objects.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

from .base import LLMProvider, Usage


@dataclass
class _AIMessage:
    """Minimal AIMessage-alike returned by invoke(). Has .content and .usage_metadata."""
    content: str
    usage_metadata: dict


def _to_dicts(messages: list) -> list[dict]:
    result = []
    for m in messages:
        if isinstance(m, dict):
            result.append(m)
        elif hasattr(m, "type") and hasattr(m, "content"):
            role = {"human": "user", "ai": "assistant", "system": "system"}.get(m.type, "user")
            result.append({"role": role, "content": m.content})
        else:
            result.append({"role": "user", "content": str(m)})
    return result


class LangChainCompat:
    """Thin shim so existing code can call .invoke(langchain_messages) unchanged."""

    def __init__(self, provider: LLMProvider):
        self._provider = provider

    @property
    def provider(self) -> LLMProvider:
        return self._provider

    def invoke(self, messages: list, config: Any = None) -> _AIMessage:
        resp = self._provider.complete(_to_dicts(messages))
        return _AIMessage(
            content=resp.content,
            usage_metadata={
                "input_tokens":  resp.usage.input_tokens,
                "output_tokens": resp.usage.output_tokens,
            },
        )

    def stream(self, messages: list, config: Any = None) -> Iterator[str]:
        yield from self._provider.stream(_to_dicts(messages))


class LLMProxy:
    """
    Module-level singleton used as the `llm` object throughout core/.
    Lazily creates a LangChainCompat wrapping the configured provider.
    Call .reload() after changing config so the next invoke() picks up the new model.
    """

    def __init__(self):
        self._compat: LangChainCompat | None = None

    def _get_compat(self) -> LangChainCompat:
        if self._compat is None:
            from majestic.llm import get_provider
            self._compat = LangChainCompat(get_provider())
        return self._compat

    def invoke(self, messages: list, config: Any = None) -> _AIMessage:
        return self._get_compat().invoke(messages)

    def stream(self, messages: list, config: Any = None) -> Iterator[str]:
        yield from self._get_compat().stream(messages)

    @property
    def provider(self) -> LLMProvider:
        return self._get_compat().provider

    def reload(self) -> None:
        self._compat = None
