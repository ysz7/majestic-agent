"""Workflow scheduler.

Runs workflows whose trigger node is a cron schedule. Backed by APScheduler's
``AsyncIOScheduler`` so jobs fire inside the background agent's event loop and
can drive :func:`majestic.orchestration.workflow_runner.run_workflow_async` directly.

Lifecycle:
  - ``start()``          create the scheduler and schedule all cron workflows.
  - ``reload(profile)``  re-scan a profile's workflows.json after a save/delete.
  - ``shutdown()``       stop the scheduler on agent shutdown.

A workflow is scheduled when it contains a trigger node with
``data.subtype == "cron"`` and a valid cron expression in ``data.schedule``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_PROFILES_ROOT = Path(__file__).resolve().parent.parent.parent / "profiles"


def _workflows_file(profile: str) -> Path:
    return _PROFILES_ROOT / profile / "data" / "workflows.json"


def _load_workflows(profile: str) -> list[dict]:
    f = _workflows_file(profile)
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return []


def _cron_expr(workflow: dict) -> str | None:
    """Return the cron expression of a workflow's cron trigger, or None."""
    for node in workflow.get("nodes", []):
        data = node.get("data", {})
        if node.get("type") == "triggerNode" and data.get("subtype") == "cron":
            expr = (data.get("schedule") or "").strip()
            return expr or None
    return None


class WorkflowScheduler:
    """Schedules cron-triggered workflows for one or more profiles."""

    def __init__(self, channel) -> None:
        self._channel = channel
        self._scheduler = AsyncIOScheduler()
        self._started = False

    def start(self, profiles: list[str]) -> None:
        if not self._started:
            self._scheduler.start()
            self._started = True
        for profile in profiles:
            self.reload(profile)

    def reload(self, profile: str) -> None:
        """Re-register all cron workflows for *profile* (idempotent)."""
        if not self._started:
            return
        # Drop existing jobs for this profile, then re-add from disk.
        prefix = f"wf:{profile}:"
        for job in self._scheduler.get_jobs():
            if job.id.startswith(prefix):
                self._scheduler.remove_job(job.id)

        for wf in _load_workflows(profile):
            expr = _cron_expr(wf)
            if not expr:
                continue
            try:
                trigger = CronTrigger.from_crontab(expr)
            except ValueError:
                logger.warning(
                    "Workflow %s has invalid cron '%s' — skipped", wf.get("id"), expr
                )
                continue
            self._scheduler.add_job(
                self._run,
                trigger=trigger,
                id=f"{prefix}{wf['id']}",
                args=[wf, profile],
                replace_existing=True,
                misfire_grace_time=300,
            )
            logger.info(
                "Scheduled workflow %s (%s) on '%s'", wf.get("name"), wf.get("id"), expr
            )

    async def _run(self, workflow: dict, profile: str) -> None:
        from majestic.orchestration.workflow_runner import run_workflow_async

        await run_workflow_async(workflow, profile, self._channel)

    def shutdown(self) -> None:
        if self._started:
            self._scheduler.shutdown(wait=False)
            self._started = False
