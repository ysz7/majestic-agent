"""
Sub-agent delegation — run isolated tasks in parallel child agents.

Each sub-agent gets its own AgentLoop + fresh session.
Parent stop_event propagates to all active children.
Max 3 concurrent sub-agents (configurable via _MAX_WORKERS).
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeout
from typing import Optional

from majestic.tools.registry import tool

_MAX_WORKERS     = 3
_SUBTASK_TIMEOUT = 60   # seconds — hard ceiling per sub-task
_MAX_ITER_SUB    = 3    # sub-agents: minimal iterations to cut token cost

# Registry of active child stop events — parent signals all on /stop
_active_children: list[threading.Event] = []
_children_lock   = threading.Lock()


def _register_child(ev: threading.Event) -> None:
    with _children_lock:
        _active_children.append(ev)


def _unregister_child(ev: threading.Event) -> None:
    with _children_lock:
        try:
            _active_children.remove(ev)
        except ValueError:
            pass


def stop_all_children() -> None:
    """Called when parent loop receives /stop — propagates to sub-agents."""
    with _children_lock:
        for ev in _active_children:
            ev.set()


@tool(
    name="delegate_task",
    description=(
        "Run a task in a sub-agent or delegate it to a named agent in the network. "
        "Use 'to' to route to a specific agent (name from registry or http://... URL). "
        "Without 'to', runs a local sub-agent (HEAVY — extra LLM calls). "
        "Do NOT use for simple lookups or single-tool operations."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The task description",
            },
            "context": {
                "type": "string",
                "description": "Optional context or data to pass to the agent",
            },
            "to": {
                "type": "string",
                "description": (
                    "Target agent — registered name (e.g. 'finance_bot') or URL "
                    "(e.g. 'http://10.0.0.2:8081'). Omit to run locally."
                ),
            },
        },
        "required": ["task"],
    },
)
def delegate_task(task: str, context: str = "", to: str = "") -> str:
    """Route task to a named/remote agent, or run locally as a sub-agent."""
    if to:
        return _delegate_to_network(task, context, to)
    # Auto-route if delegates_to configured and keyword matches
    from majestic.cli.agents import pick_delegate
    auto = pick_delegate(task)
    if auto:
        return _delegate_to_network(task, context, auto)
    # Local sub-agent fallback
    stop_ev = threading.Event()
    _register_child(stop_ev)
    try:
        return _run_subtask(task, context, stop_ev)
    finally:
        _unregister_child(stop_ev)


@tool(
    name="delegate_parallel",
    description=(
        "VERY HEAVY: spawns up to 3 parallel agents — each costs extra LLM calls and tokens. "
        "Use ONLY for genuinely parallel multi-source research (e.g. research 3 different markets at once). "
        "Do NOT use for: DB checks, simple questions, single-tool calls, answering from history. "
        "When in doubt, do the work inline instead of delegating."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of task descriptions to run in parallel",
            },
        },
        "required": ["tasks"],
    },
)
def delegate_parallel(tasks: list[str]) -> str:
    """Run up to _MAX_WORKERS tasks concurrently. Returns combined results."""
    if not tasks:
        return "(no tasks)"

    stop_events = [threading.Event() for _ in tasks]
    for ev in stop_events:
        _register_child(ev)

    results: list[str] = [f"[timed out after {_SUBTASK_TIMEOUT}s]"] * len(tasks)
    overall_timeout = _SUBTASK_TIMEOUT * min(len(tasks), _MAX_WORKERS)

    try:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
            future_to_idx = {
                executor.submit(_run_subtask, task, "", stop_events[i]): i
                for i, task in enumerate(tasks)
            }
            try:
                for future in as_completed(future_to_idx, timeout=overall_timeout):
                    idx = future_to_idx[future]
                    try:
                        results[idx] = future.result()
                    except Exception as e:
                        results[idx] = f"[sub-agent error] {e}"
            except FutureTimeout:
                # Signal all remaining sub-agents to stop so threads exit quickly
                for ev in stop_events:
                    ev.set()
    finally:
        for ev in stop_events:
            _unregister_child(ev)

    parts = [f"**Task {i+1}:** {tasks[i]}\n{results[i]}" for i in range(len(tasks))]
    return "\n\n---\n\n".join(parts)


# ── Network delegation ────────────────────────────────────────────────────────

def _delegate_to_network(task: str, context: str, target: str) -> str:
    """POST task to a named or remote agent's /api/chat endpoint."""
    import json as _json
    import urllib.request
    import urllib.error
    from majestic.cli.agents import find_agent_url

    url = find_agent_url(target)
    if not url:
        return f"[delegate error] Agent '{target}' not found in registry or not reachable."

    chat_url = url.rstrip("/") + "/api/chat"
    message  = f"Context:\n{context}\n\nTask:\n{task}" if context.strip() else task
    payload  = _json.dumps({"message": message}).encode()
    req = urllib.request.Request(
        chat_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode()
            # SSE stream — collect last 'data:' line with answer
            answer = _parse_sse_answer(body)
            return f"[{target}] {answer}"
    except urllib.error.URLError as e:
        return f"[delegate error] Could not reach '{target}' at {chat_url}: {e.reason}"
    except Exception as e:
        return f"[delegate error] {e}"


def _parse_sse_answer(body: str) -> str:
    """Extract answer text from an SSE stream or plain JSON response."""
    import json as _json
    # Try plain JSON first
    try:
        data = _json.loads(body)
        return data.get("answer") or data.get("content") or body[:500]
    except Exception:
        pass
    # SSE: find last 'data: {...}' line with an 'answer' key
    answer = ""
    for line in body.splitlines():
        if line.startswith("data:"):
            try:
                chunk = _json.loads(line[5:].strip())
                if "answer" in chunk:
                    answer = chunk["answer"]
                elif chunk.get("type") == "text":
                    answer += chunk.get("text", "")
            except Exception:
                pass
    return answer or body[:500]


# ── Local sub-agent execution ─────────────────────────────────────────────────

def _run_subtask(
    task: str,
    context: str,
    stop_event: threading.Event,
) -> str:
    from majestic.agent.loop import AgentLoop
    from majestic.agent.prompt import build_sub_system
    from majestic.config import get

    if stop_event.is_set():
        return "[Stopped before start]"

    input_text = f"Context:\n{context}\n\nTask:\n{task}" if context.strip() else task
    system = build_sub_system(lang=get("language", "EN"))

    loop = AgentLoop(stop_event=stop_event, max_iterations=_MAX_ITER_SUB)
    result = loop.run(input_text, system=system)
    return result.get("answer", "(no output)")
