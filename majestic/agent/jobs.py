"""Job Registry — single registry for all background tasks.

Every autonomous background operation (reflection, signals, cron, scripts)
goes through start_job() so the user can see all agent activity in one place.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

_jobs: dict[str, "Job"] = {}
_lock  = threading.Lock()
_MAX   = 200
_PRUNE = 50


@dataclass
class Job:
    id:          str
    type:        str        # "script" | "cron" | "reflect" | "signal" | "custom"
    name:        str
    status:      str        # "running" | "done" | "failed" | "cancelled"
    started_at:  int
    finished_at: int | None        = None
    result:      str | None        = None
    error:       str | None        = None
    _cancel:     bool              = field(default=False, repr=False)

    def should_cancel(self) -> bool:
        return self._cancel

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "type":        self.type,
            "name":        self.name,
            "status":      self.status,
            "started_at":  self.started_at,
            "finished_at": self.finished_at,
            "result":      (self.result or "")[:500] if self.result else None,
            "error":       self.error,
        }


def start_job(type_: str, name: str, fn: Callable[["Job"], None]) -> str:
    """Start fn in a daemon thread, register in registry. Returns job_id."""
    job_id = uuid.uuid4().hex[:12]
    job    = Job(id=job_id, type=type_, name=name,
                 status="running", started_at=int(time.time()))
    with _lock:
        _jobs[job_id] = job
        _prune_if_needed()

    def _run() -> None:
        try:
            fn(job)
            with _lock:
                if job.status == "running":
                    job.status      = "done"
                    job.finished_at = int(time.time())
        except Exception as e:
            with _lock:
                job.status      = "failed"
                job.error       = str(e)[:400]
                job.finished_at = int(time.time())
        _persist(job)

    threading.Thread(target=_run, daemon=True, name=f"job-{name}").start()
    return job_id


def get_job(job_id: str) -> "Job | None":
    return _jobs.get(job_id)


def list_jobs(limit: int = 50) -> list[dict]:
    with _lock:
        ordered = sorted(_jobs.values(), key=lambda j: j.started_at, reverse=True)
    return [j.to_dict() for j in ordered[:limit]]


def cancel_job(job_id: str) -> bool:
    job = _jobs.get(job_id)
    if not job or job.status != "running":
        return False
    with _lock:
        job._cancel     = True
        job.status      = "cancelled"
        job.finished_at = int(time.time())
    _persist(job)
    return True


def _prune_if_needed() -> None:
    if len(_jobs) <= _MAX:
        return
    done = sorted(
        (j for j in _jobs.values() if j.status in ("done", "failed", "cancelled")),
        key=lambda j: j.started_at,
    )
    for old in done[:_PRUNE]:
        _jobs.pop(old.id, None)


def _persist(job: "Job") -> None:
    try:
        import json
        from majestic.constants import WORKSPACE_DIR
        log = WORKSPACE_DIR / ".jobs.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(job.to_dict()) + "\n")
    except Exception:
        pass
