"""Desktop API — skills manager: list, create, update, delete (hot-reload aware)."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException

from ._auth import require_token

router = APIRouter(prefix="/skills", tags=["skills"])

_PROFILES_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "profiles"


def _skills_dir(profile: str) -> Path:
    d = _PROFILES_ROOT / profile
    if not d.exists():
        raise HTTPException(status_code=404, detail=f"Profile '{profile}' not found")
    skills = d / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    return skills


@router.get("/{profile}")
async def list_skills(profile: str, _: None = Depends(require_token)) -> dict:
    sdir = _skills_dir(profile)
    skills = []
    for f in sorted(sdir.glob("*.yaml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            data["_filename"] = f.name
            skills.append(data)
        except Exception:
            skills.append({"_filename": f.name, "name": f.stem, "_parse_error": True})
    return {"skills": skills}


@router.post("/{profile}")
async def create_skill(
    profile: str, body: dict, _: None = Depends(require_token)
) -> dict:
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")

    sdir = _skills_dir(profile)
    filename = f"{name.replace(' ', '_').lower()}.yaml"
    path = sdir / filename
    if path.exists():
        raise HTTPException(status_code=409, detail=f"Skill '{name}' already exists")

    path.write_text(
        yaml.dump(body, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    return {"status": "created", "filename": filename}


@router.put("/{profile}/{name}")
async def update_skill(
    profile: str, name: str, body: dict, _: None = Depends(require_token)
) -> dict:
    sdir = _skills_dir(profile)
    # accept both "skill_name" and "skill_name.yaml"
    stem = name.removesuffix(".yaml")
    path = sdir / f"{stem}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Skill '{stem}' not found")

    path.write_text(
        yaml.dump(body, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    return {"status": "updated", "filename": path.name}


@router.delete("/{profile}/{name}")
async def delete_skill(
    profile: str, name: str, _: None = Depends(require_token)
) -> dict:
    sdir = _skills_dir(profile)
    stem = name.removesuffix(".yaml")
    path = sdir / f"{stem}.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Skill '{stem}' not found")

    path.unlink()
    return {"status": "deleted", "filename": path.name}
