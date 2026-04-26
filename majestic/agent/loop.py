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


class AgentLoop:
    def __init__(
        self,
        stop_event: Optional[threading.Event] = None,
        max_iterations: int = MAX_ITERATIONS,
    ):
        self._stop      = stop_event or threading.Event()
        self._max_iter  = max_iterations

    def stop(self) -> None:
        self._stop.set()
        try:
            from majestic.agent.delegate import stop_all_children
            stop_all_children()
        except Exception:
            pass

    def run(
        self,
        user_input: str,
        session_id: Optional[str] = None,
        history: Optional[list[tuple[str, str]]] = None,
        on_tool_call: Optional[Callable[[str, dict], None]] = None,
        system: Optional[str] = None,
    ) -> dict:
        from majestic.llm import get_provider
        import majestic.tools as _tools
        from majestic.config import get

        provider     = get_provider()
        tool_schemas = _tools.get_schemas()

        if system is None:
            from majestic.memory.store import load_both
            from majestic.agent.prompt import build_system
            system = build_system(lang=get("language", "EN"), memory=load_both())

        # Build initial messages from history (last 5 turns for context)
        messages = _build_initial_messages(user_input, history)

        # Save user message to DB
        if session_id:
            _save_msg(session_id, "user", user_input)

        sources: list[str] = []
        iterations = 0

        while iterations < self._max_iter:
            if self._stop.is_set():
                return {"answer": "[Stopped by user.]", "sources": sources}

            iterations += 1

            resp = provider.complete(
                messages=_prune_old_tool_results(messages),
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

            # Append tool results (cap size to avoid context bloat)
            for tc in resp.tool_calls:
                result_text = tool_results.get(tc.id, "[no result]")
                if session_id:
                    _save_msg(session_id, "tool", result_text, tool_name=tc.name)
                messages.append({
                    "role":         "tool_result",
                    "tool_call_id": tc.id,
                    "content":      _cap_tool_result(tc.name, result_text),
                })

        # Safety: max iterations reached
        return {"answer": "Reached maximum tool-call iterations.", "sources": sources}


# ── Helpers ───────────────────────────────────────────────────────────────────

_HIST_ANSWER_MAX = 800   # chars — long briefings/reports are trimmed in history context
_HIST_USER_MAX   = 300


def _trim(text: str, limit: int) -> str:
    return text[:limit] + "…[truncated]" if len(text) > limit else text


def _build_initial_messages(
    user_input: str,
    history: Optional[list[tuple[str, str]]],
) -> list[dict]:
    msgs: list[dict] = []
    for u, a in (history or [])[-4:]:   # 4 turns keeps context without bloating
        msgs.append({"role": "user",      "content": _trim(u, _HIST_USER_MAX)})
        msgs.append({"role": "assistant", "content": _trim(a, _HIST_ANSWER_MAX)})
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


_TOOL_RESULT_MAX   = 6000
_TOOL_RESULT_SMALL = 2000
_PRUNE_AFTER = 2   # prune older batches once there are more than N tool_result msgs


def _prune_old_tool_results(messages: list[dict]) -> list[dict]:
    """Replace older tool_result contents with 1-line summaries before sending to LLM.

    Keeps the most recent batch (last assistant-with-tools → its results) at full size.
    Earlier results are collapsed to a single line — no LLM call needed.
    """
    tool_result_count = sum(1 for m in messages if m.get("role") == "tool_result")
    if tool_result_count <= _PRUNE_AFTER:
        return messages

    # Find start index of the last tool-call batch
    last_batch = -1
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "assistant" and messages[i].get("tool_calls"):
            last_batch = i
            break
    if last_batch == -1:
        return messages

    pruned = []
    for i, msg in enumerate(messages):
        if msg.get("role") == "tool_result" and i < last_batch:
            content = msg.get("content", "")
            # Take first non-empty line, cap at 120 chars
            first = next((ln[:120] for ln in content.splitlines() if ln.strip()), content[:120])
            suffix = f" … ({len(content):,} chars)" if len(content) > 120 else ""
            pruned.append({**msg, "content": f"[pruned] {first}{suffix}"})
        else:
            pruned.append(msg)
    return pruned


def _cap_tool_result(name: str, text: str) -> str:
    limit = _TOOL_RESULT_SMALL if name in (
        "get_briefing", "get_report", "generate_ideas",
        "run_research", "get_news", "delegate_parallel", "delegate_task",
    ) else _TOOL_RESULT_MAX
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…[output truncated — {len(text)} chars total]"


def _save_msg(session_id: str, role: str, content: str, **kwargs) -> None:
    try:
        from majestic.db.state import StateDB
        StateDB().add_message(session_id, role, content, **kwargs)
    except Exception:
        pass


def _track(resp) -> None:
    try:
        from majestic.token_tracker import track
        from majestic.llm import get_provider
        um = resp.usage
        if not um:
            return
        cost = None
        try:
            cost = get_provider().estimated_cost(um)
        except Exception:
            pass
        track(
            um.input_tokens or 0,
            um.output_tokens or 0,
            "agent_loop",
            cache_write=um.cache_write_tokens or 0,
            cache_read=um.cache_read_tokens or 0,
            cost_override=cost,
        )
    except Exception:
        pass
