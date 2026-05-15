"""
majestic.cli.ps
~~~~~~~~~~~~~~~
List all agent daemons tracked in data/registry.json and show their status.
"""

from __future__ import annotations

import os
import sys

from majestic import display
from majestic.cli.registry_db import load_registry


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
    registry = load_registry()

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
