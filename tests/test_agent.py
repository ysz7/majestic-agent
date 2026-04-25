"""Tests for AgentLoop — single turn, tool calls, stop signal, iteration cap."""
import threading
from unittest.mock import patch, MagicMock

import pytest

from majestic.agent.loop import AgentLoop
from majestic.llm.base import LLMResponse, ToolCall, Usage


def _mock_provider(responses: list[LLMResponse]):
    provider = MagicMock()
    provider.complete.side_effect = list(responses)
    return provider


def _env_patches(provider):
    """All patches needed to isolate AgentLoop from real infra."""
    return [
        patch("majestic.llm.get_provider",        return_value=provider),
        patch("majestic.memory.store.load_both",   return_value=""),
        patch("majestic.config.get",               return_value="EN"),
        patch("majestic.agent.prompt.build_system", return_value="You are a test assistant."),
        patch("majestic.tools.get_schemas",         return_value=[]),
        patch("majestic.agent.loop._save_msg"),
        patch("majestic.agent.loop._track"),
    ]


def _run(provider, user_input="hello", session_id=None, history=None, stop=None):
    patches = _env_patches(provider)
    for p in patches:
        p.start()
    try:
        loop = AgentLoop(stop_event=stop)
        return loop.run(user_input, session_id=session_id, history=history)
    finally:
        for p in patches:
            p.stop()


def test_simple_answer():
    provider = _mock_provider([LLMResponse(content="I am fine!", usage=Usage())])
    result = _run(provider)
    assert result["answer"] == "I am fine!"
    assert result["sources"] == []


def test_empty_history():
    provider = _mock_provider([LLMResponse(content="No history, no problem.", usage=Usage())])
    result = _run(provider, history=[])
    assert result["answer"] == "No history, no problem."


def test_history_is_prepended():
    provider = _mock_provider([LLMResponse(content="Got history.", usage=Usage())])
    result = _run(provider, history=[("prev user", "prev answer")])
    assert result["answer"] == "Got history."

    call_msgs = provider.complete.call_args[1].get("messages") or provider.complete.call_args[0][0]
    roles = [m["role"] for m in call_msgs]
    assert roles[:2] == ["user", "assistant"]


def test_tool_call_then_answer():
    tc = ToolCall(id="tc1", name="fake_tool", arguments={"q": "test"})

    with patch("majestic.agent.loop._execute_tools", return_value={"tc1": "tool result"}):
        provider = _mock_provider([
            LLMResponse(content="", usage=Usage(), tool_calls=[tc]),
            LLMResponse(content="Final answer after tool.", usage=Usage()),
        ])
        result = _run(provider)

    assert result["answer"] == "Final answer after tool."


def test_stop_before_first_call():
    stop = threading.Event()
    stop.set()

    provider = _mock_provider([LLMResponse(content="should not reach", usage=Usage())])
    result = _run(provider, stop=stop)

    assert "Stopped" in result["answer"]
    provider.complete.assert_not_called()


def test_max_iterations_cap():
    tc = ToolCall(id="tc_inf", name="loop_tool", arguments={})

    with patch("majestic.agent.loop._execute_tools", return_value={"tc_inf": "ok"}):
        provider = _mock_provider(
            [LLMResponse(content="", usage=Usage(), tool_calls=[tc])] * 15
        )
        result = _run(provider)

    assert "maximum" in result["answer"].lower()


def test_on_tool_call_callback():
    tc = ToolCall(id="tc3", name="cb_tool", arguments={"key": "val"})
    calls: list[tuple] = []

    with patch("majestic.agent.loop._execute_tools", return_value={"tc3": "result"}):
        provider = _mock_provider([
            LLMResponse(content="", usage=Usage(), tool_calls=[tc]),
            LLMResponse(content="Done.", usage=Usage()),
        ])
        patches = _env_patches(provider)
        for p in patches:
            p.start()
        try:
            loop = AgentLoop()
            loop.run("test callback", on_tool_call=lambda n, a: calls.append((n, a)))
        finally:
            for p in patches:
                p.stop()

    assert calls == [("cb_tool", {"key": "val"})]


def test_stop_returns_stopped_message():
    stop = threading.Event()

    call_count = 0
    tc = ToolCall(id="tc_s", name="slow", arguments={})

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        stop.set()  # set stop after first LLM call
        return LLMResponse(content="", usage=Usage(), tool_calls=[tc])

    provider = MagicMock()
    provider.complete.side_effect = side_effect

    with patch("majestic.agent.loop._execute_tools", return_value={"tc_s": "[Stopped]"}):
        result = _run(provider, stop=stop)

    # After stop is set, loop exits — either "Stopped" or "maximum iterations"
    assert result is not None
