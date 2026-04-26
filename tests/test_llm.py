"""Tests for LLM abstraction layer — ToolCall parsing, mock provider."""
import pytest
from majestic.llm.base import LLMProvider, LLMResponse, ToolCall, Usage


class MockProvider(LLMProvider):
    """Deterministic provider for testing."""

    def __init__(self, responses: list[LLMResponse]):
        self._responses = list(responses)
        self._calls: list[dict] = []

    @property
    def model_id(self) -> str:
        return "mock-1"

    def complete(self, messages, system="", max_tokens=4096, tools=None) -> LLMResponse:
        self._calls.append({"messages": messages, "system": system, "tools": tools})
        if self._responses:
            return self._responses.pop(0)
        return LLMResponse(content="(no response)", usage=Usage())

    def stream(self, messages, system="", max_tokens=4096):
        yield "(stream)"


def test_toolcall_dataclass():
    tc = ToolCall(id="call_1", name="search_web", arguments={"query": "test"})
    assert tc.id   == "call_1"
    assert tc.name == "search_web"
    assert tc.arguments["query"] == "test"


def test_usage_total():
    u = Usage(input_tokens=100, output_tokens=50)
    assert u.total == 150


def test_usage_with_cache():
    u = Usage(input_tokens=100, output_tokens=50, cache_read_tokens=20, cache_write_tokens=10)
    assert u.total == 150  # total = in + out only


def test_llm_response_defaults():
    resp = LLMResponse(content="hello", usage=Usage())
    assert resp.finish_reason == "stop"
    assert resp.tool_calls    == []
    assert resp.model         == ""


def test_mock_provider_complete():
    provider = MockProvider([
        LLMResponse(content="Hello, world!", usage=Usage(input_tokens=10, output_tokens=5)),
    ])
    resp = provider.complete(messages=[{"role": "user", "content": "hi"}])
    assert resp.content == "Hello, world!"
    assert len(provider._calls) == 1
    assert provider._calls[0]["messages"][0]["role"] == "user"


def test_mock_provider_with_tool_calls():
    tc = ToolCall(id="tc1", name="search_web", arguments={"query": "ai news"})
    provider = MockProvider([
        LLMResponse(content="", usage=Usage(), tool_calls=[tc]),
        LLMResponse(content="Found results.", usage=Usage()),
    ])

    resp1 = provider.complete([{"role": "user", "content": "search for ai news"}])
    assert len(resp1.tool_calls) == 1
    assert resp1.tool_calls[0].name == "search_web"

    resp2 = provider.complete([{"role": "user", "content": "continue"}])
    assert resp2.content == "Found results."
    assert resp2.tool_calls == []


def test_mock_provider_estimated_cost():
    provider = MockProvider([])
    assert provider.estimated_cost(Usage(input_tokens=1000, output_tokens=500)) == 0.0


def test_mock_provider_stream():
    provider = MockProvider([])
    chunks = list(provider.stream([{"role": "user", "content": "hi"}]))
    assert chunks == ["(stream)"]


# ── OpenAI provider unit tests (no network) ───────────────────────────────────

def test_openai_provider_registered():
    from majestic.llm.base import _registry
    assert "openai" in _registry


def test_openai_provider_model_id():
    from majestic.llm.openai import OpenAIProvider
    p = OpenAIProvider(model="gpt-4o-mini")
    assert p.model_id == "gpt-4o-mini"


def test_openai_provider_estimated_cost():
    from majestic.llm.openai import OpenAIProvider
    p = OpenAIProvider(model="gpt-4o")
    cost = p.estimated_cost(Usage(input_tokens=1_000_000, output_tokens=1_000_000))
    assert abs(cost - 12.50) < 0.01  # 2.50 in + 10.00 out


def test_openai_provider_cost_unknown_model():
    from majestic.llm.openai import OpenAIProvider
    p = OpenAIProvider(model="gpt-future-9000")
    cost = p.estimated_cost(Usage(input_tokens=1_000_000, output_tokens=1_000_000))
    assert cost > 0  # falls back to default pricing


def test_openrouter_provider_registered():
    from majestic.llm.base import _registry
    assert "openrouter" in _registry


def test_openrouter_tool_conversion():
    from majestic.llm.openrouter import OpenRouterProvider
    tools = [{"name": "search_web", "description": "Search", "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}}}]
    converted = OpenRouterProvider._convert_tools(tools)
    assert converted[0]["type"] == "function"
    assert converted[0]["function"]["name"] == "search_web"
    assert "parameters" in converted[0]["function"]


def test_openrouter_message_conversion_tool_result():
    from majestic.llm.openrouter import OpenRouterProvider
    msgs = [{"role": "tool_result", "tool_call_id": "tc1", "content": "result text"}]
    converted = OpenRouterProvider._convert_messages(msgs)
    assert converted[0]["role"] == "tool"
    assert converted[0]["tool_call_id"] == "tc1"


def test_all_providers_registered():
    from majestic.llm.base import _registry
    for name in ("anthropic", "openai", "openrouter", "ollama"):
        assert name in _registry, f"Provider '{name}' not registered"
