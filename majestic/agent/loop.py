"""Agentic loop — LLM + tool calls, up to 10 iterations. Parallel tool execution via ThreadPoolExecutor."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from majestic.llm.base import LLMResponse, ToolCall

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
        on_file_artifact: Optional[Callable[[str, str], None]] = None,
        system: Optional[str] = None,
    ) -> dict:
        from majestic.llm import get_provider
        import majestic.tools as _tools
        from majestic.config import get

        provider     = get_provider()
        tool_schemas = _tools.get_schemas()
        is_local     = type(provider).__name__ == "OllamaProvider"

        if system is None:
            from majestic.memory.store import load_both
            from majestic.agent.prompt import build_system
            system = build_system(lang=get("language", "EN"), memory=load_both())

        # Inject per-project context from AGENTS.md if present in cwd
        try:
            import os; from pathlib import Path as _P
            _ctx = (_P(os.getcwd()) / "AGENTS.md").read_text(encoding="utf-8").strip()
            if _ctx:
                system += f"\n\n[Project context]\n{_ctx}"
        except Exception:
            pass

        messages = _build_initial_messages(user_input, history)
        if session_id:
            _save_msg(session_id, "user", user_input)

        sources: list[str] = []; tools_used: list[str] = []; iterations = 0

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
                # If model only emitted a tag with no real content, retry with a nudge
                content = resp.content or ""
                if is_local and _is_empty_response(content) and iterations < self._max_iter:
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user",
                                     "content": "Your response was empty. Please provide a full answer in plain text."})
                    continue
                if session_id:
                    _save_msg(session_id, "assistant", content, finish_reason=resp.finish_reason)
                    _fire_background(session_id, content, list(tools_used))
                return {"answer": content, "sources": sources}

            # Drop tool calls with names not in the offered schema (hallucinations / MCP browser)
            resp = _filter_tool_calls(resp, tool_schemas, session_id, sources, tools_used)
            if not resp.tool_calls:
                if session_id: _save_msg(session_id, "assistant", resp.content or ""); _fire_background(session_id, resp.content or "", list(tools_used))
                return {"answer": resp.content, "sources": sources}

            # ── Execute tool calls ────────────────────────────────────────────
            for tc in resp.tool_calls:
                tools_used.append(tc.name)
            if on_tool_call:
                for tc in resp.tool_calls:
                    on_tool_call(tc.name, tc.arguments)

            tool_results = _execute_tools(resp.tool_calls, self._stop, is_local)

            # Emit file artifact events for write_file results
            if on_file_artifact:
                for tc in resp.tool_calls:
                    if tc.name == "write_file":
                        artifact = _parse_file_artifact(tool_results.get(tc.id, ""))
                        if artifact:
                            on_file_artifact(*artifact)

            # Collect sources from knowledge/web tool results
            for tc in resp.tool_calls:
                if tc.name in (
                    "search_knowledge", "search_web", "get_market_data",
                    "run_research", "get_news", "get_briefing", "get_report", "generate_ideas",
                ):
                    sources.append(tc.name)

            messages.append({
                "role": "assistant", "content": resp.content or "",
                "tool_calls": [{"id": tc.id, "name": tc.name, "arguments": tc.arguments} for tc in resp.tool_calls],
            })
            for tc in resp.tool_calls:
                result_text = tool_results.get(tc.id, "[no result]")
                if session_id: _save_msg(session_id, "tool", result_text, tool_name=tc.name)
                messages.append({"role": "tool_result", "tool_call_id": tc.id,
                                  "content": _cap_tool_result(tc.name, result_text, is_local)})

        # Safety: max iterations reached
        return {"answer": "Reached maximum tool-call iterations.", "sources": sources}


# ── Helpers ───────────────────────────────────────────────────────────────────

_HIST_ANSWER_MAX = 1500  # chars — long briefings/reports are trimmed in history context
_HIST_USER_MAX   = 500


def _trim(text: str, limit: int) -> str:
    return text[:limit] + "…[truncated]" if len(text) > limit else text


def _build_initial_messages(user_input: str, history: Optional[list[tuple[str, str]]]) -> list[dict]:
    msgs: list[dict] = []
    for u, a in (history or [])[-8:]:
        msgs.append({"role": "user",      "content": _trim(u, _HIST_USER_MAX)})
        msgs.append({"role": "assistant", "content": _trim(a, _HIST_ANSWER_MAX)})
    msgs.append({"role": "user", "content": user_input})
    return msgs


def _is_empty_response(content: str) -> bool:
    import re as _re
    return len(_re.sub(r'\[confidence:\s*\w+\]', '', content).strip()) < 20


def _execute_tools(tool_calls: list[ToolCall], stop_event: threading.Event,
                   is_local: bool = False) -> dict[str, str]:
    import majestic.tools as _tools
    if stop_event.is_set():
        return {tc.id: "[Stopped]" for tc in tool_calls}
    if len(tool_calls) == 1:
        tc = tool_calls[0]
        return {tc.id: _tools.execute(tc.name, tc.arguments)}
    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(_tools.execute, tc.name, tc.arguments): tc
                   for tc in tool_calls if not stop_event.is_set()}
        for future, tc in [(f, futures[f]) for f in futures]:
            try: results[tc.id] = future.result(timeout=30)
            except Exception as e: results[tc.id] = f"[tool error] {e}"
    return results


_TOOL_RESULT_MAX        = 6000
_TOOL_RESULT_SMALL      = 2000
_TOOL_RESULT_LOCAL_MAX  = 1500   # local models have small context — keep results short
_TOOL_RESULT_LOCAL_SMALL = 800
_PRUNE_AFTER = 2


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


_SMALL_TOOLS = {"get_briefing", "get_report", "generate_ideas", "run_research",
                "get_news", "delegate_parallel", "delegate_task"}


def _cap_tool_result(name: str, text: str, is_local: bool = False) -> str:
    if is_local:
        limit = _TOOL_RESULT_LOCAL_SMALL if name in _SMALL_TOOLS else _TOOL_RESULT_LOCAL_MAX
    else:
        limit = _TOOL_RESULT_SMALL if name in _SMALL_TOOLS else _TOOL_RESULT_MAX
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…[truncated — {len(text)} chars total]"


def _save_msg(session_id: str, role: str, content: str, **kwargs) -> None:
    try:
        from majestic.db.state import StateDB
        StateDB().add_message(session_id, role, content, **kwargs)
    except Exception:
        pass


def _parse_file_artifact(result: str) -> tuple[str, str] | None:
    import re; from pathlib import Path; from majestic.constants import WORKSPACE_DIR
    m = re.match(r"(?:Written|Appended to) (.+?) \(\d+ chars\)", result)
    if not m:
        return None
    p = Path(m.group(1))
    try:
        return str(p.relative_to(WORKSPACE_DIR)), p.name
    except ValueError:
        return p.name, p.name


def _fire_background(session_id: str, answer: str, tools_used: list[str]) -> None:
    from majestic.agent.jobs import start_job
    def _sig(job) -> None:
        try:
            from majestic.profile.signals import collect_signals; collect_signals(session_id)
        except Exception:
            pass
    start_job("signal", f"signals:{session_id[:8]}", _sig)
    try:
        from majestic.config import get as _g
        if _g("agent.reflect", True) and len(tools_used) >= int(_g("agent.reflect_min_tools", 3)):
            def _ref(job) -> None:
                from majestic.agent.reflection import reflect_session
                reflect_session(session_id, answer, tools_used)
            start_job("reflect", f"reflect:{session_id[:8]}", _ref)
    except Exception:
        pass


def _track(resp) -> None:
    try:
        from majestic.token_tracker import track
        from majestic.llm import get_provider
        um = resp.usage
        if not um: return
        try: cost = get_provider().estimated_cost(um)
        except Exception: cost = None
        track(um.input_tokens or 0, um.output_tokens or 0, "agent_loop",
              cache_write=um.cache_write_tokens or 0, cache_read=um.cache_read_tokens or 0,
              cost_override=cost)
    except Exception: pass


def _filter_tool_calls(resp: "LLMResponse", tool_schemas, session_id, sources, tools_used) -> "LLMResponse":
    """Remove tool calls whose names are not in the offered schema (hallucinations / MCP browser)."""
    if not tool_schemas:
        return resp
    valid_names = {t.get("name") for t in tool_schemas}
    valid = [tc for tc in resp.tool_calls if tc.name in valid_names]
    invalid = [tc.name for tc in resp.tool_calls if tc.name not in valid_names]
    if not invalid:
        return resp
    note = f"\n(attempted unknown tools: {', '.join(invalid)})"
    return LLMResponse(content=(resp.content or "") + note, usage=resp.usage,
                       finish_reason=resp.finish_reason, model=resp.model, tool_calls=valid)
