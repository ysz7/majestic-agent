"""Desktop API — cron job management (stored as JSON per profile)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from ._auth import require_token

router = APIRouter(prefix="/cron", tags=["cron"])

_PROFILES_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "profiles"


def _cron_file(profile: str) -> Path:
    data_dir = _PROFILES_ROOT / profile / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "cron_jobs.json"


def _load(profile: str) -> list[dict]:
    f = _cron_file(profile)
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(profile: str, jobs: list[dict]) -> None:
    _cron_file(profile).write_text(
        json.dumps(jobs, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _ensure_profile(profile: str) -> None:
    if not (_PROFILES_ROOT / profile).exists():
        raise HTTPException(status_code=404, detail=f"Profile '{profile}' not found")


@router.get("/{profile}")
async def list_cron_jobs(profile: str, _: None = Depends(require_token)) -> dict:
    _ensure_profile(profile)
    return {"jobs": _load(profile)}


@router.post("/{profile}")
async def create_cron_job(profile: str, body: dict, _: None = Depends(require_token)) -> dict:
    _ensure_profile(profile)
    job: dict = {
        "id":         str(uuid.uuid4()),
        "schedule":   str(body.get("schedule") or "0 9 * * *"),
        "task":       str(body.get("task") or ""),
        "active":     bool(body.get("active", True)),
        "agent":      str(body.get("agent") or profile),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_run":   None,
    }
    jobs = _load(profile)
    jobs.append(job)
    _save(profile, jobs)
    return {"status": "created", "job": job}


@router.put("/{profile}/{job_id}")
async def update_cron_job(
    profile: str, job_id: str, body: dict, _: None = Depends(require_token)
) -> dict:
    _ensure_profile(profile)
    jobs = _load(profile)
    for job in jobs:
        if job["id"] == job_id:
            for key in ("schedule", "task", "active", "agent"):
                if key in body:
                    job[key] = body[key]
            _save(profile, jobs)
            return {"status": "updated", "job": job}
    raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")


@router.delete("/{profile}/{job_id}")
async def delete_cron_job(
    profile: str, job_id: str, _: None = Depends(require_token)
) -> dict:
    _ensure_profile(profile)
    jobs = _load(profile)
    new_jobs = [j for j in jobs if j["id"] != job_id]
    if len(new_jobs) == len(jobs):
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    _save(profile, new_jobs)
    return {"status": "deleted"}
