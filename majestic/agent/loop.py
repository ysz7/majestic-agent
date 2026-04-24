"""
Agentic loop — the core execution engine.

Flow: user input → LLM (with tools) → tool calls → results → LLM → ... → final answer
Each iteration is tracked in the messages table. Parallel tool execution via ThreadPoolExecutor.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from majestic.llm.base import ToolCall

MAX_ITERATIONS = 10

_SYSTEM = """\
You are Majestic, a universal AI agent. You have access to tools to help answer questions and complete tasks.

Guidelines:
- Answer directly from your knowledge when you already know the answer.
- Use tools when you need specific information: documents, web data, market prices.
- For multi-step tasks, use multiple tools in sequence or parallel.
- Be concise and structured in your final answer.
- If a tool returns no useful data, say so and answer from what you know.\
"""


class AgentLoop:
    def __init__(self, stop_event: Optional[threading.Event] = None):
        self._stop = stop_event or threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(
        self,
        user_input: str,
        session_id: Optional[str] = None,
        history: Optional[list[tuple[str, str]]] = None,
        on_tool_call: Optional[Callable[[str, dict], None]] = None,
    ) -> dict:
        from core.rag_engine import llm as _proxy
        import majestic.tools as _tools
        from majestic.memory.store import load_both
        from core.config import get_lang

        provider = _proxy.provider
        tool_schemas = _tools.get_schemas()

        # Build system prompt with memory and language
        memory = load_both()
        lang = get_lang()
        system = _SYSTEM + f"\n\nRespond in {lang}."
        if memory:
            system += f"\n\n## Persistent memory\n{memory}"

        # Build initial messages from history (last 5 turns for context)
        messages = _build_initial_messages(user_input, history)

        # Save user message to DB
        if session_id:
            _save_msg(session_id, "user", user_input)

        sources: list[str] = []
        iterations = 0

        while iterations < MAX_ITERATIONS:
            if self._stop.is_set():
                return {"answer": "[Stopped by user.]", "sources": sources}

            iterations += 1

            resp = provider.complete(
                messages=messages,
                system=system,
                max_tokens=4096,
                tools=tool_schemas or None,
            )

            # Track tokens
            _track(resp)

            if not resp.tool_calls:
                # Final answer — no more tool calls
                if session_id:
                    _save_msg(session_id, "assistant", resp.content,
                              finish_reason=resp.finish_reason)
                return {"answer": resp.content, "sources": sources}

            # ── Execute tool calls ────────────────────────────────────────────
            if on_tool_call:
                for tc in resp.tool_calls:
                    on_tool_call(tc.name, tc.arguments)

            tool_results = _execute_tools(resp.tool_calls, self._stop)

            # Collect sources from knowledge/web tool results
            for tc in resp.tool_calls:
                if tc.name in (
                    "search_knowledge", "search_web", "get_market_data",
                    "run_research", "get_news", "get_briefing", "get_report", "generate_ideas",
                ):
                    sources.append(tc.name)

            # Append assistant message (with tool calls) to conversation
            messages.append({
                "role":       "assistant",
                "content":    resp.content or "",
                "tool_calls": [
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                    for tc in resp.tool_calls
                ],
            })

            # Append tool results
            for tc in resp.tool_calls:
                result_text = tool_results.get(tc.id, "[no result]")
                messages.append({
                    "role":         "tool_result",
                    "tool_call_id": tc.id,
                    "content":      result_text,
                })
                if session_id:
                    _save_msg(session_id, "tool", result_text, tool_name=tc.name)

        # Safety: max iterations reached
        return {"answer": "Reached maximum tool-call iterations.", "sources": sources}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_initial_messages(
    user_input: str,
    history: Optional[list[tuple[str, str]]],
) -> list[dict]:
    msgs: list[dict] = []
    for u, a in (history or [])[-5:]:
        msgs.append({"role": "user",      "content": u})
        msgs.append({"role": "assistant", "content": a})
    msgs.append({"role": "user", "content": user_input})
    return msgs


def _execute_tools(
    tool_calls: list[ToolCall],
    stop_event: threading.Event,
) -> dict[str, str]:
    import majestic.tools as _tools

    if stop_event.is_set():
        return {tc.id: "[Stopped]" for tc in tool_calls}

    if len(tool_calls) == 1:
        tc = tool_calls[0]
        return {tc.id: _tools.execute(tc.name, tc.arguments)}

    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_tools.execute, tc.name, tc.arguments): tc
            for tc in tool_calls
            if not stop_event.is_set()
        }
        for future, tc in [(f, futures[f]) for f in futures]:
            try:
                results[tc.id] = future.result(timeout=30)
            except Exception as e:
                results[tc.id] = f"[tool error] {e}"
    return results


def _save_msg(session_id: str, role: str, content: str, **kwargs) -> None:
    try:
        from majestic.db.state import StateDB
        StateDB().add_message(session_id, role, content, **kwargs)
    except Exception:
        pass


def _track(resp) -> None:
    try:
        from majestic.llm.compat import _AIMessage
        from core.token_tracker import track_response
        track_response(
            _AIMessage(resp.content, {
                "input_tokens":  resp.usage.input_tokens,
                "output_tokens": resp.usage.output_tokens,
            }),
            "agent_loop",
        )
    except Exception:
        pass
