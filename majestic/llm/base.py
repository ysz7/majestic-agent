"""
Core LLM abstractions: Usage, ToolCall, LLMResponse, LLMProvider, and provider registry.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict  # pre-parsed JSON


@dataclass
class LLMResponse:
    content: str
    usage: Usage
    finish_reason: str = "stop"
    model: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMProvider(ABC):
    @abstractmethod
    def complete(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> LLMResponse: ...

    @abstractmethod
    def stream(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 4096,
    ) -> Iterator[str]: ...

    @property
    @abstractmethod
    def model_id(self) -> str: ...

    def estimated_cost(self, usage: Usage) -> float:
        return 0.0


_registry: dict[str, type[LLMProvider]] = {}


def register(name: str):
    def decorator(cls: type[LLMProvider]) -> type[LLMProvider]:
        _registry[name] = cls
        return cls
    return decorator


def get_provider(name: str, **kwargs) -> LLMProvider:
    cls = _registry.get(name)
    if not cls:
        raise ValueError(f"Unknown LLM provider: {name!r}. Available: {sorted(_registry)}")
    return cls(**kwargs)
