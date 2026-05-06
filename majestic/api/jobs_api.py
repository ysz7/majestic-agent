"""Schedule API handlers."""
from __future__ import annotations


def handle_list_schedules() -> dict:
    try:
        from majestic.cron.jobs import list_schedules
        return {"schedules": list_schedules()}
    except Exception:
        return {"schedules": []}
