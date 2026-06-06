"""Desktop API — running agents: list, start, stop."""

from __future__ import annotations

import sys

from fastapi import APIRouter, Depends, HTTPException

from ._auth import require_token

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/running")
async def running_agents(_: None = Depends(require_token)) -> dict:
    from majestic.cli.registry_db import load_registry

    return {"agents": list(load_registry().values())}


@router.post("/{name}/start")
async def start_agent(name: str, _: None = Depends(require_token)) -> dict:
    import subprocess

    from majestic.cli.registry_db import load_registry

    if name in load_registry():
        return {"status": "already_running", "profile": name}

    flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    proc = subprocess.Popen(
        [sys.executable, "-m", "majestic", "run", name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )
    return {"status": "starting", "profile": name, "pid": proc.pid}


@router.post("/{name}/stop")
async def stop_agent(name: str, _: None = Depends(require_token)) -> dict:
    from majestic.cli.registry_db import load_registry

    if name not in load_registry():
        raise HTTPException(status_code=404, detail=f"Agent '{name}' is not running")

    try:
        from majestic.cli.stop import run as _stop

        _stop(name)
    except SystemExit:
        pass
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {"status": "stopped", "profile": name}
