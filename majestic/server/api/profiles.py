"""Desktop API — profile management (list, create, delete, persona CRUD)."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException

from ._auth import require_token

router = APIRouter(prefix="/profiles", tags=["profiles"])

_PROFILES_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "profiles"


def _profiles_dir() -> Path:
    _PROFILES_ROOT.mkdir(parents=True, exist_ok=True)
    return _PROFILES_ROOT


@router.get("")
async def list_profiles(_: None = Depends(require_token)) -> dict:
    from majestic.cli.registry_db import load_registry

    registry = load_registry()
    profiles = []
    for d in sorted(_profiles_dir().iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        entry = registry.get(d.name, {})
        persona_file = d / "persona.yaml"
        display_name = d.name
        role = ""
        if persona_file.exists():
            try:
                p = yaml.safe_load(persona_file.read_text(encoding="utf-8")) or {}
                display_name = p.get("name", d.name)
                role = p.get("role", "")
            except Exception:
                pass
        profiles.append(
            {
                "profile": d.name,
                "name": display_name,
                "role": role,
                "running": bool(entry),
                "port": entry.get("port"),
                "pid": entry.get("pid"),
                "started_at": entry.get("started_at"),
            }
        )
    return {"profiles": profiles}


@router.post("/new")
async def create_profile(body: dict, _: None = Depends(require_token)) -> dict:
    profile_name = (body.get("name") or "").strip()
    if not profile_name:
        raise HTTPException(status_code=400, detail="name required")

    d = _profiles_dir() / profile_name
    if d.exists():
        raise HTTPException(status_code=409, detail=f"Profile '{profile_name}' already exists")

    d.mkdir(parents=True)
    (d / "skills").mkdir()
    (d / "workspace").mkdir()
    (d / "data").mkdir()

    persona: dict = {
        "name": body.get("display_name") or profile_name,
        "role": body.get("role") or "General purpose AI assistant",
        "tone": body.get("tone") or "helpful, concise",
        "language": body.get("language") or "en",
        "port": body.get("port") or 8000,
        "limits": {
            "max_tokens_per_task": 0,
            "max_cost_per_task": 0.0,
        },
    }
    (d / "persona.yaml").write_text(
        yaml.dump(persona, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    (d / ".env").write_text("# API keys for this profile\n", encoding="utf-8")
    return {"status": "created", "profile": profile_name}


@router.delete("/{name}")
async def delete_profile(name: str, _: None = Depends(require_token)) -> dict:
    import shutil

    d = _profiles_dir() / name
    if not d.exists():
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")

    from majestic.cli.registry_db import load_registry

    if name in load_registry():
        raise HTTPException(
            status_code=409,
            detail=f"Agent '{name}' is running — stop it before deleting",
        )

    shutil.rmtree(d)
    return {"status": "deleted", "profile": name}


@router.get("/{name}/persona")
async def get_persona(name: str, _: None = Depends(require_token)) -> dict:
    persona_file = _profiles_dir() / name / "persona.yaml"
    if not persona_file.exists():
        raise HTTPException(status_code=404, detail="persona.yaml not found")
    return yaml.safe_load(persona_file.read_text(encoding="utf-8")) or {}


@router.put("/{name}/persona")
async def update_persona(name: str, body: dict, _: None = Depends(require_token)) -> dict:
    d = _profiles_dir() / name
    if not d.exists():
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    (d / "persona.yaml").write_text(
        yaml.dump(body, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    return {"status": "updated"}


@router.get("/{name}/env")
async def get_env(name: str, _: None = Depends(require_token)) -> dict:
    """Return .env key-value pairs; sensitive values masked."""
    env_file = _profiles_dir() / name / ".env"
    if not env_file.exists():
        return {"entries": []}
    _SENSITIVE = ("KEY", "SECRET", "TOKEN", "PASSWORD", "PASS", "PWD")
    entries = []
    for line in env_file.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, _, val = raw.partition("=")
        key = key.strip()
        val = val.strip()
        sensitive = any(w in key.upper() for w in _SENSITIVE)
        entries.append({"key": key, "value": val, "masked": sensitive})
    return {"entries": entries}


@router.put("/{name}/env")
async def update_env(name: str, body: dict, _: None = Depends(require_token)) -> dict:
    """Write .env from entries list [{key, value}]."""
    d = _profiles_dir() / name
    if not d.exists():
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    lines = ["# API keys for this profile\n"]
    for entry in body.get("entries", []):
        key = str(entry.get("key", "")).strip()
        val = str(entry.get("value", "")).strip()
        if key:
            lines.append(f"{key}={val}\n")
    (d / ".env").write_text("".join(lines), encoding="utf-8")
    return {"status": "updated"}
