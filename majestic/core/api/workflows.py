"""Desktop API — workflow CRUD (stored as JSON per profile)."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from ._auth import require_token

router = APIRouter(prefix="/workflows", tags=["workflows"])

_PROFILES_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "profiles"


def _wf_file(profile: str) -> Path:
    data_dir = _PROFILES_ROOT / profile / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "workflows.json"


def _load(profile: str) -> list[dict]:
    f = _wf_file(profile)
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(profile: str, workflows: list[dict]) -> None:
    _wf_file(profile).write_text(
        json.dumps(workflows, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _ensure_profile(profile: str) -> None:
    if not (_PROFILES_ROOT / profile).exists():
        raise HTTPException(status_code=404, detail=f"Profile '{profile}' not found")


def _reload_schedule(request: Request, profile: str) -> None:
    """Re-register cron workflows after a change (no-op without a scheduler)."""
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is not None:
        try:
            scheduler.reload(profile)
        except Exception:  # noqa: BLE001
            pass


@router.get("/{profile}")
async def list_workflows(profile: str, _: None = Depends(require_token)) -> dict:
    _ensure_profile(profile)
    return {"workflows": _load(profile)}


@router.post("/{profile}")
async def create_workflow(
    profile: str, body: dict, request: Request, _: None = Depends(require_token)
) -> dict:
    _ensure_profile(profile)
    now = datetime.now(timezone.utc).isoformat()
    wf: dict = {
        "id":         str(uuid.uuid4())[:8],
        "name":       str(body.get("name") or "Untitled"),
        "nodes":      body.get("nodes") or [],
        "edges":      body.get("edges") or [],
        "created_at": now,
        "updated_at": now,
    }
    workflows = _load(profile)
    workflows.append(wf)
    _save(profile, workflows)
    _reload_schedule(request, profile)
    return {"status": "created", "workflow": wf}


@router.put("/{profile}/{wf_id}")
async def update_workflow(
    profile: str, wf_id: str, body: dict, request: Request, _: None = Depends(require_token)
) -> dict:
    _ensure_profile(profile)
    workflows = _load(profile)
    for wf in workflows:
        if wf["id"] == wf_id:
            wf["name"]       = str(body.get("name") or wf["name"])
            wf["nodes"]      = body.get("nodes", wf["nodes"])
            wf["edges"]      = body.get("edges", wf["edges"])
            wf["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save(profile, workflows)
            _reload_schedule(request, profile)
            return {"status": "updated", "workflow": wf}
    raise HTTPException(status_code=404, detail=f"Workflow '{wf_id}' not found")


@router.delete("/{profile}/{wf_id}")
async def delete_workflow(
    profile: str, wf_id: str, request: Request, _: None = Depends(require_token)
) -> dict:
    _ensure_profile(profile)
    workflows = _load(profile)
    new_wfs = [w for w in workflows if w["id"] != wf_id]
    if len(new_wfs) == len(workflows):
        raise HTTPException(status_code=404, detail=f"Workflow '{wf_id}' not found")
    _save(profile, new_wfs)
    _reload_schedule(request, profile)
    return {"status": "deleted"}


@router.post("/{profile}/{wf_id}/run")
async def run_workflow(
    profile: str, wf_id: str, request: Request, _: None = Depends(require_token)
) -> dict:
    """Trigger a workflow manually — runs it in the background, streaming progress over WS."""
    _ensure_profile(profile)
    workflows = _load(profile)
    wf = next((w for w in workflows if w["id"] == wf_id), None)
    if wf is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{wf_id}' not found")

    channel = getattr(request.app.state, "channel", None)
    if channel is None:
        raise HTTPException(
            status_code=503,
            detail="Workflow execution requires the background agent (majestic run).",
        )

    from majestic.core.workflow_runner import run_workflow_async

    asyncio.create_task(run_workflow_async(wf, profile, channel))
    return {"status": "started", "workflow_id": wf_id}
