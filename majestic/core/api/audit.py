"""Desktop API — audit log (tool call history from checkpoint store)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ._auth import require_token

router = APIRouter(prefix="/audit", tags=["audit"])

_PROFILES_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "profiles"


def _db(profile: str) -> Path:
    return _PROFILES_ROOT / profile / "data" / "checkpoints.db"


def _load_audit(profile: str, limit: int, tool_filter: str | None) -> list[dict[str, Any]]:
    db_path = _db(profile)
    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Latest checkpoint per task = highest step_num
        rows = conn.execute(
            """
            SELECT task_id, step_num, step_data, created_at
            FROM checkpoints
            WHERE (task_id, step_num) IN (
                SELECT task_id, MAX(step_num) FROM checkpoints GROUP BY task_id
            )
            ORDER BY created_at DESC
            LIMIT 100
            """
        ).fetchall()
    finally:
        conn.close()

    entries: list[dict] = []
    for row in rows:
        try:
            data = json.loads(row["step_data"])
        except Exception:
            continue
        steps: list[dict] = data.get("steps", [])
        for step in steps:
            tool = str(step.get("tool", ""))
            if tool_filter and tool != tool_filter:
                continue
            args = step.get("args", {})
            args_str = ", ".join(f"{k}={str(v)[:40]}" for k, v in (args.items() if isinstance(args, dict) else []))
            result_str = str(step.get("result", ""))[:120]
            entries.append(
                {
                    "task_id":      row["task_id"],
                    "created_at":   row["created_at"],
                    "tool":         tool,
                    "args_preview": args_str[:80],
                    "result_preview": result_str,
                }
            )

    # Sort newest first, apply limit
    entries.sort(key=lambda e: e["created_at"], reverse=True)
    return entries[:limit]


@router.get("/{profile}")
async def get_audit(
    profile: str,
    limit: int = 50,
    tool: str | None = None,
    _: None = Depends(require_token),
) -> dict:
    if not (_PROFILES_ROOT / profile).exists():
        raise HTTPException(status_code=404, detail=f"Profile '{profile}' not found")
    return {"entries": _load_audit(profile, limit, tool)}
