"""
majestic.cli.ps
~~~~~~~~~~~~~~~
List all agent daemons tracked in data/registry.json and show their status.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from majestic import display

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_REGISTRY = _PROJECT_ROOT / "data" / "registry.json"


def _load_registry() -> dict:
    if _REGISTRY.exists():
        try:
            return json.loads(_REGISTRY.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _is_process_alive(pid: int) -> bool:
    try:
        if sys.platform == "win32":
            import ctypes
            SYNCHRONIZE = 0x00100000
            handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        else:
            os.kill(pid, 0)
            return True
    except (OSError, ProcessLookupError, PermissionError):
        return False


def run() -> None:
    registry = _load_registry()

    agents = []
    stale: list[str] = []

    for profile_name, entry in registry.items():
        pid = entry.get("pid")
        alive = bool(pid and _is_process_alive(pid))
        if not alive:
            stale.append(profile_name)
        agents.append({
            "name": profile_name,
            "port": entry.get("port", "?"),
            "pid": pid,
            "status": "running" if alive else "dead",
            "started_at": entry.get("started_at", ""),
        })

    display.print_agents_table(agents)

    if stale:
        display.warn(
            f"{len(stale)} entry/entries appear dead. "
            "They will be cleaned up automatically on next  majestic stop."
        )
