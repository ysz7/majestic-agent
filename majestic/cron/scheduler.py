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
        name    = schedule["name"]
        prompt  = schedule["prompt"]
        target  = schedule.get("delivery_target") or "cli"
        logger.info(f"Running schedule '{name}': {prompt!r}")

        try:
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

    # Full AgentLoop for arbitrary prompts
    from majestic.agent.loop import AgentLoop
    result = AgentLoop().run(prompt)
    return result.get("answer", "(no answer)")


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
