"""Desktop API — memory viewer: episodic, lessons, user profile."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ._auth import require_token

router = APIRouter(prefix="/memory", tags=["memory"])

_VALID_TYPES = {"episodic", "lessons", "profile"}


def _settings(profile: str):
    from majestic.config.settings import Settings

    try:
        return Settings(profile)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Profile '{profile}' not found")


# ── episodic ─────────────────────────────────────────────────────────────────

@router.get("/{profile}/episodic")
async def get_episodic(
    profile: str,
    q: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    _: None = Depends(require_token),
) -> dict:
    s = _settings(profile)
    from majestic.storage import get_backend

    db = get_backend(s).episodic()
    try:
        entries = db.search(q, limit=limit) if q else db.get_recent(limit=limit)
    finally:
        db.close()
    return {"entries": entries}


@router.delete("/{profile}/episodic/{entry_id}")
async def delete_episodic_entry(
    profile: str, entry_id: int, _: None = Depends(require_token)
) -> dict:
    s = _settings(profile)
    from majestic.storage import get_backend

    db = get_backend(s).episodic()
    try:
        db._conn.execute("DELETE FROM tasks WHERE id = ?", (entry_id,))
        db._conn.execute(
            "INSERT INTO tasks_fts(tasks_fts, rowid) VALUES ('delete', ?)", (entry_id,)
        )
        db._conn.commit()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        db.close()
    return {"status": "deleted", "id": entry_id}


# ── lessons ───────────────────────────────────────────────────────────────────

@router.get("/{profile}/lessons")
async def get_lessons(
    profile: str,
    q: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=200),
    _: None = Depends(require_token),
) -> dict:
    s = _settings(profile)
    from majestic.storage import get_backend

    db = get_backend(s).lessons()
    try:
        entries = db.search(q, limit=limit) if q else db.get_top(limit=limit)
    finally:
        db._conn.close()
    return {"entries": entries}


@router.delete("/{profile}/lessons/{entry_id}")
async def delete_lesson(
    profile: str, entry_id: int, _: None = Depends(require_token)
) -> dict:
    s = _settings(profile)
    from majestic.storage import get_backend

    db = get_backend(s).lessons()
    try:
        db._conn.execute("DELETE FROM lessons WHERE id = ?", (entry_id,))
        db._conn.commit()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        db._conn.close()
    return {"status": "deleted", "id": entry_id}


# ── user profile ──────────────────────────────────────────────────────────────

@router.get("/{profile}/profile")
async def get_user_profile(profile: str, _: None = Depends(require_token)) -> dict:
    s = _settings(profile)
    from majestic.storage import get_backend

    db = get_backend(s).user_profile()
    try:
        data = db.get_all()
    finally:
        db._conn.close()
    return {"profile": data}


@router.delete("/{profile}/profile/{key}")
async def delete_profile_key(
    profile: str, key: str, _: None = Depends(require_token)
) -> dict:
    s = _settings(profile)
    from majestic.storage import get_backend

    db = get_backend(s).user_profile()
    try:
        db.delete(key)
    finally:
        db._conn.close()
    return {"status": "deleted", "key": key}


# ── clear (any type) ──────────────────────────────────────────────────────────

@router.post("/{profile}/clear")
async def clear_memory(
    profile: str, body: dict, _: None = Depends(require_token)
) -> dict:
    mem_type = body.get("type", "")
    if mem_type not in _VALID_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"type must be one of {sorted(_VALID_TYPES)}",
        )

    s = _settings(profile)
    from majestic.storage import get_backend

    backend = get_backend(s)

    if mem_type == "episodic":
        db = backend.episodic()
        try:
            db._conn.execute("DELETE FROM tasks")
            db._conn.execute("INSERT INTO tasks_fts(tasks_fts) VALUES ('rebuild')")
            db._conn.commit()
        finally:
            db.close()

    elif mem_type == "lessons":
        db = backend.lessons()
        try:
            db._conn.execute("DELETE FROM lessons")
            db._conn.commit()
        finally:
            db._conn.close()

    elif mem_type == "profile":
        db = backend.user_profile()
        try:
            db._conn.execute("DELETE FROM user_profile")
            db._conn.commit()
        finally:
            db._conn.close()

    return {"status": "cleared", "type": mem_type}
