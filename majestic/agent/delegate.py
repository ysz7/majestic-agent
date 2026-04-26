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
        "HEAVY: spawns a separate agent (uses extra LLM calls + tokens). "
        "Use ONLY when a task is truly independent and too complex for a single tool call. "
        "Do NOT use for simple lookups, DB checks, or single-tool operations — call the tool directly instead."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The task description for the sub-agent",
            },
            "context": {
                "type": "string",
                "description": "Optional context or data to pass to the sub-agent",
            },
        },
        "required": ["task"],
    },
)
def delegate_task(task: str, context: str = "") -> str:
    """Run a single task in an isolated sub-agent. Returns the answer."""
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


# ── Core execution ────────────────────────────────────────────────────────────

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
