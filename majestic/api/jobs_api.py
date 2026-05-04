"""Jobs, reflections, schedules, and script-stats API handlers."""
from __future__ import annotations

import re


def handle_list_jobs() -> dict:
    from majestic.agent.jobs import list_jobs
    return {"jobs": list_jobs(50)}


def handle_cancel_job(job_id: str) -> dict:
    if not re.match(r'^[a-f0-9]{12}$', job_id):
        return {"ok": False, "error": "invalid job_id"}
    from majestic.agent.jobs import cancel_job
    return {"ok": cancel_job(job_id)}


def handle_list_reflections() -> dict:
    from majestic.constants import WORKSPACE_DIR
    d = WORKSPACE_DIR / ".reflections"
    if not d.exists():
        return {"reflections": []}
    files = sorted(d.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return {"reflections": [
        {"id": p.stem, "name": p.name, "modified_at": int(p.stat().st_mtime)}
        for p in files[:20]
    ]}


def handle_get_reflection(rid: str) -> dict:
    if not re.match(r'^[\w\-]+$', rid):
        return {"error": "invalid id"}
    from majestic.constants import WORKSPACE_DIR
    p = WORKSPACE_DIR / ".reflections" / f"{rid}.md"
    if not p.exists():
        return {"error": "not found"}
    return {"id": rid, "content": p.read_text(encoding="utf-8")}


def handle_script_stats() -> dict:
    try:
        from majestic.tools.scripts.metrics import get_all_stats
        return {"stats": get_all_stats()}
    except Exception:
        return {"stats": {}}


def handle_list_schedules() -> dict:
    try:
        from majestic.cron.jobs import list_schedules
        return {"schedules": list_schedules()}
    except Exception:
        return {"schedules": []}


def stream_jobs(wfile, flush_fn) -> None:
    """Blocking SSE — yields job_update events every 2 s when jobs change."""
    import json
    import time
    from majestic.agent.jobs import list_jobs
    last: str = ""
    while True:
        try:
            payload = json.dumps(
                {"type": "job_update", "jobs": list_jobs(50)}, ensure_ascii=False
            )
            if payload != last:
                last = payload
                wfile.write(f"data: {payload}\n\n".encode())
                flush_fn()
        except Exception:
            break
        time.sleep(2)
