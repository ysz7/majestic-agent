"""Desktop API — budget: current token + cost usage for a profile."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ._auth import require_token

router = APIRouter(prefix="/budget", tags=["budget"])


@router.get("/{profile}")
async def get_budget(profile: str, _: None = Depends(require_token)) -> dict:
    from majestic.config.settings import Settings

    try:
        s = Settings(profile)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Profile '{profile}' not found")

    from majestic.storage import get_backend

    backend = get_backend(s)

    # Limits from persona.yaml
    limits = s._persona.get("limits", {}) if hasattr(s, "_persona") else {}
    max_tokens = limits.get("max_tokens_per_task", 0)
    max_cost = limits.get("max_cost_per_task", 0.0)

    # Recent usage from episodic history (last 10 tasks)
    total_tokens = 0
    total_cost = 0.0
    recent_tasks: list[dict] = []
    try:
        ep = backend.episodic()
        recent_tasks = ep.get_recent(limit=10)
        ep.close()
        for t in recent_tasks:
            total_tokens += t.get("tokens_used", 0)
            total_cost += t.get("cost", 0.0)
    except Exception:
        pass

    return {
        "profile": profile,
        "limits": {
            "max_tokens_per_task": max_tokens,
            "max_cost_per_task": max_cost,
        },
        "recent_10_tasks": {
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 6),
            "task_count": len(recent_tasks),
        },
    }
