"""
Cron scheduler — background thread that runs due schedules every minute.

Usage:
    scheduler = CronScheduler(delivery={"telegram": notify_fn, "cli": print})
    scheduler.start()
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

logger = logging.getLogger(__name__)

_TICK = 60  # seconds between due-schedule checks


class CronScheduler:
    def __init__(self, delivery: dict[str, Callable[[str], None]] | None = None):
        self._delivery = delivery or {}
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="cron-scheduler"
        )
        self._thread.start()
        logger.info("CronScheduler started.")

    def stop(self) -> None:
        self._stop.set()

    def register_delivery(self, target: str, fn: Callable[[str], None]) -> None:
        self._delivery[target] = fn

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as e:
                logger.error(f"CronScheduler tick error: {e}")
            self._stop.wait(_TICK)

    def _tick(self) -> None:
        from majestic.cron.jobs import get_due, mark_ran
        due = get_due()
        for schedule in due:
            try:
                mark_ran(schedule["id"])
                threading.Thread(
                    target=self._run_schedule,
                    args=(schedule,),
                    daemon=True,
                    name=f"cron-{schedule['name']}",
                ).start()
            except Exception as e:
                logger.error(f"Failed to start schedule {schedule['name']}: {e}")

    def _run_schedule(self, schedule: dict) -> None:
        name     = schedule["name"]
        prompt   = schedule["prompt"]
        target   = schedule.get("delivery_target") or "cli"
        parallel = bool(schedule.get("parallel"))
        raw_sub  = schedule.get("subtasks")
        logger.info(f"Running schedule '{name}': {prompt!r} parallel={parallel}")

        try:
            if parallel and raw_sub:
                import json as _json
                subtasks = _json.loads(raw_sub) if isinstance(raw_sub, str) else raw_sub
                result = _execute_parallel(subtasks) if subtasks else _execute_prompt(prompt)
            else:
                result = _execute_prompt(prompt)
        except Exception as e:
            result = f"Schedule '{name}' failed: {e}"
            logger.error(result)

        header = f"⏰ Schedule: {name}\n\n"
        self._deliver(target, header + result)

    def _deliver(self, target: str, text: str) -> None:
        fn = self._delivery.get(target) or self._delivery.get("cli") or print
        try:
            fn(text)
        except Exception as e:
            logger.error(f"Delivery to '{target}' failed: {e}")


# ── Prompt execution ──────────────────────────────────────────────────────────

# Maps common shorthand prompts to tool names for direct execution (no LLM loop)
_SHORTHAND: dict[str, str] = {
    "briefing":  "get_briefing",
    "research":  "run_research",
    "market":    "get_market_data",
    "news":      "get_news",
    "ideas":     "generate_ideas",
}


def _execute_prompt(prompt: str) -> str:
    """Run a schedule prompt. Shorthand → direct tool call; else → AgentLoop."""
    import majestic.tools as tools

    key = prompt.strip().lower()
    if key in _SHORTHAND:
        return tools.execute(_SHORTHAND[key], {})

    from majestic.agent.loop import AgentLoop
    result = AgentLoop().run(prompt)
    return result.get("answer", "(no answer)")


_SUBTASK_TIMEOUT = 120  # seconds per parallel subtask


def _execute_parallel(subtasks: list[str]) -> str:
    """Run subtasks concurrently, wait for all, combine results."""
    import threading

    results: list[str] = [f"[timed out after {_SUBTASK_TIMEOUT}s]"] * len(subtasks)

    def _run(i: int, task: str) -> None:
        try:
            results[i] = _execute_prompt(task)
        except Exception as e:
            results[i] = f"[error] {e}"

    threads = [
        threading.Thread(target=_run, args=(i, t), daemon=True)
        for i, t in enumerate(subtasks)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=_SUBTASK_TIMEOUT)

    parts = [f"**{subtasks[i]}**\n{results[i]}" for i in range(len(subtasks))]
    return "\n\n---\n\n".join(parts)


# ── Module-level singleton ────────────────────────────────────────────────────

_scheduler: CronScheduler | None = None


def get_scheduler() -> CronScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = CronScheduler()
    return _scheduler


def start_scheduler(delivery: dict[str, Callable] | None = None) -> CronScheduler:
    """Create (or return) the global scheduler, register delivery targets, start it."""
    s = get_scheduler()
    for target, fn in (delivery or {}).items():
        s.register_delivery(target, fn)
    s.start()
    return s
