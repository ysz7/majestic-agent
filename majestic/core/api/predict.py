"""Desktop API — Predict v2 reports (single-section forecasts).

  GET  /predict/{profile}          list saved reports (date + summary)
  GET  /predict/{profile}/{date}   full report (markdown + parsed items)
  POST /predict/{profile}/run      generate now (returns the report)

Reports stored under ``profiles/<name>/workspace/predictions/<date>.{md,json}``.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from ._auth import require_token

router = APIRouter(prefix="/predict", tags=["predict"])

_PROFILES_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "profiles"


def _pred_dir(profile: str) -> Path:
    return _PROFILES_ROOT / profile / "workspace" / "predictions"


def _ensure_profile(profile: str) -> None:
    if not (_PROFILES_ROOT / profile).exists():
        raise HTTPException(status_code=404, detail=f"Profile '{profile}' not found")


@router.get("/{profile}")
async def list_reports(profile: str, _: None = Depends(require_token)) -> dict:
    _ensure_profile(profile)
    d = _pred_dir(profile)
    reports = []
    if d.exists():
        for f in sorted(d.glob("*.json"), reverse=True):
            if f.stem.startswith("_"):
                continue
            try:
                items = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                items = []
            reports.append({"date": f.stem, "count": len(items)})
    return {"reports": reports}


@router.get("/{profile}/{report_date}")
async def get_report(profile: str, report_date: str, _: None = Depends(require_token)) -> dict:
    _ensure_profile(profile)
    d = _pred_dir(profile)
    jf = d / f"{report_date}.json"
    mf = d / f"{report_date}.md"
    if not jf.exists() and not mf.exists():
        raise HTTPException(status_code=404, detail=f"Report '{report_date}' not found")
    items = []
    if jf.exists():
        try:
            items = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            items = []
    markdown = mf.read_text(encoding="utf-8") if mf.exists() else ""
    return {"date": report_date, "items": items, "markdown": markdown}


@router.post("/{profile}/run")
async def run_report(profile: str, body: dict | None = None, _: None = Depends(require_token)) -> dict:
    _ensure_profile(profile)
    days = 30
    if body and isinstance(body.get("days"), int):
        days = body["days"]

    from majestic.core.intelligence.predict import run_for_profile

    try:
        return await run_for_profile(profile, days=days)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
