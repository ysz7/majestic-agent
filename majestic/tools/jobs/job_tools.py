"""Background job tools — run_script_async, list_jobs, cancel_job."""
from __future__ import annotations

from majestic.tools.registry import tool

_STR = {"type": "string"}
_INT = {"type": "integer"}
_OBJ = {"type": "object"}


@tool(
    name="run_script_async",
    description="Run a saved script in the background. Returns job_id immediately; does not block.",
    input_schema={
        "type": "object",
        "properties": {
            "name":   {**_STR, "description": "Script name (without .py)"},
            "params": {**_OBJ, "description": "Env-var params for the script", "default": {}},
        },
        "required": ["name"],
    },
)
def run_script_async(name: str, params: dict | None = None) -> str:
    from majestic.agent.jobs import start_job
    import majestic.tools as _t

    def _fn(job) -> None:
        result = _t.execute("run_script", {"name": name, "params": params or {}})
        job.result = result

    job_id = start_job("script", f"script:{name}", _fn)
    return f"job_id={job_id}  ·  script '{name}' running in background"


@tool(
    name="list_jobs",
    description="List recent background jobs (scripts, cron, reflections, signals).",
    input_schema={
        "type": "object",
        "properties": {
            "limit": {**_INT, "description": "Max jobs to return (default 20)"},
        },
    },
)
def list_jobs_tool(limit: int = 20) -> str:
    from majestic.agent.jobs import list_jobs
    jobs = list_jobs(min(limit, 50))
    if not jobs:
        return "No background jobs recorded."
    icon = {"running": "⏳", "done": "✓", "failed": "✗", "cancelled": "⊘"}
    rows = ["id           type       status     name", "─" * 58]
    for j in jobs:
        i = icon.get(j["status"], "?")
        rows.append(f"{j['id']:<13}{j['type']:<11}{i} {j['status']:<10}{j['name']}")
    return "\n".join(rows)


@tool(
    name="cancel_job",
    description="Cancel a running background job by job_id.",
    input_schema={
        "type": "object",
        "properties": {
            "job_id": {**_STR, "description": "Job ID from run_script_async or list_jobs"},
        },
        "required": ["job_id"],
    },
)
def cancel_job_tool(job_id: str) -> str:
    from majestic.agent.jobs import cancel_job
    ok = cancel_job(job_id)
    return (f"Cancelled job {job_id}." if ok
            else f"Cannot cancel {job_id} — not found or already finished.")
