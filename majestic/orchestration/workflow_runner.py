"""Workflow execution engine.

Runs a saved visual workflow (nodes + edges) by walking it in topological
order from the trigger node. Action nodes are submitted to the agent through
the channel queue and their output is passed to the next node as
``{prev_output}``. Output nodes write files, emit desktop notifications, or
forward to another agent.

Progress is streamed to connected WebSocket clients via ``emit_event``:

    {"type": "workflow_step", "workflow_id", "node", "label", "status", "output"}
    {"type": "workflow_done", "workflow_id", "result"}
    {"type": "workflow_error", "workflow_id", "message"}
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date
from pathlib import Path

from majestic.server.api.ws import emit_event

logger = logging.getLogger(__name__)

_PROFILES_ROOT = Path(__file__).resolve().parent.parent.parent / "profiles"

# Per-action agent timeout (seconds). Matches the runtime task timeout.
_ACTION_TIMEOUT = 300.0


def _topological_order(nodes: list[dict], edges: list[dict]) -> list[dict]:
    """Return nodes ordered from the trigger outward following edges.

    Falls back to the original node order for any nodes unreachable from a
    trigger (defensive — a well-formed workflow has a single trigger root).
    """
    by_id = {n["id"]: n for n in nodes}
    adjacency: dict[str, list[str]] = {n["id"]: [] for n in nodes}
    indegree: dict[str, int] = {n["id"]: 0 for n in nodes}

    for e in edges:
        src, tgt = e.get("source"), e.get("target")
        if src in adjacency and tgt in indegree:
            adjacency[src].append(tgt)
            indegree[tgt] += 1

    # Start from trigger nodes (or any node with no incoming edge).
    queue: list[str] = [
        n["id"]
        for n in nodes
        if n.get("type") == "triggerNode" or indegree[n["id"]] == 0
    ]
    seen: set[str] = set()
    ordered: list[dict] = []

    while queue:
        nid = queue.pop(0)
        if nid in seen:
            continue
        seen.add(nid)
        ordered.append(by_id[nid])
        for nxt in adjacency.get(nid, []):
            if nxt not in seen:
                queue.append(nxt)

    # Append any leftover nodes not reached above.
    for n in nodes:
        if n["id"] not in seen:
            ordered.append(n)
    return ordered


def _substitute(template: str, prev_output: str, agent_name: str) -> str:
    """Replace template variables in *template*."""
    return (
        (template or "")
        .replace("{prev_output}", prev_output)
        .replace("{date}", date.today().isoformat())
        .replace("{agent_name}", agent_name)
    )


def _build_action_task(node: dict, prev_output: str, agent_name: str) -> str:
    """Turn an action node + its config into a natural-language task for the agent."""
    data = node.get("data", {})
    subtype = data.get("subtype", "")

    if subtype == "research":
        return _substitute(data.get("query", ""), prev_output, agent_name)
    if subtype == "prompt":
        return _substitute(data.get("prompt", ""), prev_output, agent_name)
    if subtype == "http":
        method = data.get("method", "GET")
        url = _substitute(data.get("url", ""), prev_output, agent_name)
        body = _substitute(data.get("body", ""), prev_output, agent_name)
        task = f"Make an HTTP {method} request to {url}."
        if body.strip():
            task += f" Request body: {body}"
        task += " Return the response."
        return task
    if subtype == "python":
        code = _substitute(data.get("code", ""), prev_output, agent_name)
        return f"Execute this Python code and return its output:\n```python\n{code}\n```"

    # Unknown action — treat its prompt/query/label as the task.
    return _substitute(
        data.get("prompt") or data.get("query") or data.get("label") or "",
        prev_output,
        agent_name,
    )


async def _run_action(channel, task_text: str) -> str:
    """Submit *task_text* to the agent and await its result."""
    task_id = str(uuid.uuid4())
    enqueued = channel.try_enqueue({"task_id": task_id, "text": task_text})
    if not enqueued:
        return "Error: agent queue full"
    try:
        return await channel.await_result(task_id, timeout=_ACTION_TIMEOUT)
    except asyncio.TimeoutError:
        return "Error: agent timed out"


def _handle_output(node: dict, profile: str, prev_output: str, agent_name: str) -> str:
    """Execute an output node. Returns a short status string."""
    data = node.get("data", {})
    subtype = data.get("subtype", "")

    if subtype == "notify":
        title = _substitute(data.get("title", "Majestic"), prev_output, agent_name)
        body = _substitute(data.get("body", "{prev_output}"), prev_output, agent_name)
        emit_event({"type": "notify", "title": title, "body": body})
        return "notified"

    if subtype == "savefile":
        filename = _substitute(data.get("filename", "output.txt"), prev_output, agent_name)
        mode = data.get("mode", "overwrite")
        target = _PROFILES_ROOT / profile / "workspace" / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a" if mode == "append" else "w", encoding="utf-8") as fh:
            fh.write(prev_output + ("\n" if mode == "append" else ""))
        return f"saved to {filename}"

    if subtype == "agent":
        target = data.get("target", "")
        # Forwarding to another agent is delegated via the agent_client tool
        # during a normal agent run; here we record the intent.
        return f"forwarded to {target}" if target else "no target agent"

    return "unknown output"


async def run_workflow_async(workflow: dict, profile: str, channel) -> None:
    """Execute *workflow* end to end, streaming progress over the WebSocket."""
    wf_id = workflow.get("id", "")
    agent_name = profile
    nodes = workflow.get("nodes", [])
    edges = workflow.get("edges", [])

    try:
        prev_output = ""
        for node in _topological_order(nodes, edges):
            ntype = node.get("type")
            label = node.get("data", {}).get("subtype", ntype)

            if ntype == "triggerNode":
                continue

            emit_event({
                "type": "workflow_step", "workflow_id": wf_id,
                "node": node["id"], "label": label, "status": "running",
            })

            if ntype == "actionNode":
                subtype = node.get("data", {}).get("subtype", "")
                if subtype == "product_forge":
                    # Runs the Solo Product Forge service directly (not via the agent).
                    try:
                        from majestic.intelligence.products import run_for_profile

                        res = await run_for_profile(profile, days=30)
                        output = res["markdown"]
                    except Exception as exc:  # noqa: BLE001
                        output = f"Error: {exc}"
                else:
                    task_text = _build_action_task(node, prev_output, agent_name)
                    if not task_text.strip():
                        output = "Error: action node has no configured input"
                    else:
                        output = await _run_action(channel, task_text)
                prev_output = output
                emit_event({
                    "type": "workflow_step", "workflow_id": wf_id,
                    "node": node["id"], "label": label, "status": "done",
                    "output": output[:500],
                })

            elif ntype == "outputNode":
                status = _handle_output(node, profile, prev_output, agent_name)
                emit_event({
                    "type": "workflow_step", "workflow_id": wf_id,
                    "node": node["id"], "label": label, "status": "done",
                    "output": status,
                })

        emit_event({
            "type": "workflow_done", "workflow_id": wf_id,
            "result": prev_output[:1000],
        })
    except Exception as exc:  # noqa: BLE001
        logger.exception("Workflow %s failed", wf_id)
        emit_event({
            "type": "workflow_error", "workflow_id": wf_id, "message": str(exc),
        })
