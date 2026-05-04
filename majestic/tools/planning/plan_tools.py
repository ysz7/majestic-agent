"""Plan-Execute-Track tools — plan_task, update_step, get_plan."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from majestic.tools.registry import tool

_STATUS = {"todo", "in_progress", "done", "blocked"}


def _plans_dir() -> Path:
    from majestic.constants import WORKSPACE_DIR
    d = WORKSPACE_DIR / "plans"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load(plan_id: str) -> dict | None:
    p = _plans_dir() / f"{plan_id}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save(plan_id: str, plan: dict) -> None:
    (_plans_dir() / f"{plan_id}.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )


@tool(
    name="plan_task",
    description=(
        "Create a step-by-step plan for a multi-step task. "
        "Call this before executing tasks with 3 or more steps. "
        "Returns a plan_id — pass it to update_step as you complete each step."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ordered list of steps to complete the task",
            },
            "title": {
                "type": "string",
                "description": "Short title describing the overall task",
            },
        },
        "required": ["steps"],
    },
)
def plan_task(steps: list[str], title: str = "") -> str:
    if not steps:
        return "steps list cannot be empty."

    plan_id = uuid.uuid4().hex[:12]
    plan = {
        "id":    plan_id,
        "title": title or "Task plan",
        "steps": [
            {"id": i + 1, "text": s, "status": "todo", "note": ""}
            for i, s in enumerate(steps)
        ],
    }
    _save(plan_id, plan)

    lines = [f"Plan created (id: {plan_id}) — {plan['title']}"]
    for s in plan["steps"]:
        lines.append(f"  [ ] {s['id']}. {s['text']}")
    lines.append("Use update_step(plan_id, step_id, status) to track progress.")
    return "\n".join(lines)


@tool(
    name="update_step",
    description="Update the status of a step in a plan. Call after completing or blocking a step.",
    input_schema={
        "type": "object",
        "properties": {
            "plan_id": {"type": "string", "description": "Plan ID returned by plan_task"},
            "step_id": {"type": "integer", "description": "Step number (1-based)"},
            "status":  {
                "type": "string",
                "enum": ["in_progress", "done", "blocked"],
                "description": "New status for the step",
            },
            "note":    {"type": "string", "description": "Optional note (e.g. result or blocker reason)"},
        },
        "required": ["plan_id", "step_id", "status"],
    },
)
def update_step(plan_id: str, step_id: int, status: str, note: str = "") -> str:
    if status not in _STATUS:
        return f"Invalid status '{status}'. Use: {', '.join(sorted(_STATUS))}."

    plan = _load(plan_id)
    if plan is None:
        return f"Plan '{plan_id}' not found."

    updated = False
    for s in plan["steps"]:
        if s["id"] == step_id:
            s["status"] = status
            if note:
                s["note"] = note
            updated = True
            break

    if not updated:
        return f"Step {step_id} not found in plan '{plan_id}'."

    _save(plan_id, plan)

    icons = {"todo": "[ ]", "in_progress": "[→]", "done": "[✓]", "blocked": "[✗]"}
    lines = [f"Plan {plan_id} — {plan['title']}"]
    for s in plan["steps"]:
        icon = icons.get(s["status"], "[ ]")
        note_str = f" ({s['note']})" if s["note"] else ""
        lines.append(f"  {icon} {s['id']}. {s['text']}{note_str}")
    return "\n".join(lines)


@tool(
    name="get_plan",
    description="Show the current status of all steps in a plan.",
    input_schema={
        "type": "object",
        "properties": {
            "plan_id": {"type": "string", "description": "Plan ID returned by plan_task"},
        },
        "required": ["plan_id"],
    },
)
def get_plan(plan_id: str) -> str:
    plan = _load(plan_id)
    if plan is None:
        return f"Plan '{plan_id}' not found."

    icons = {"todo": "[ ]", "in_progress": "[→]", "done": "[✓]", "blocked": "[✗]"}
    lines = [f"Plan: {plan['title']} (id: {plan_id})"]
    for s in plan["steps"]:
        icon = icons.get(s["status"], "[ ]")
        note_str = f" — {s['note']}" if s["note"] else ""
        lines.append(f"  {icon} {s['id']}. {s['text']}{note_str}")
    done  = sum(1 for s in plan["steps"] if s["status"] == "done")
    total = len(plan["steps"])
    lines.append(f"Progress: {done}/{total} steps done")
    return "\n".join(lines)
