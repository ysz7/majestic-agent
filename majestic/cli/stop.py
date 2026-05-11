"""
majestic.cli.stop
~~~~~~~~~~~~~~~~~
Stop a running agent daemon by sending it a termination signal and removing
its entry from data/registry.json.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path

from majestic import display

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_REGISTRY = _PROJECT_ROOT / "data" / "registry.json"

_GRACEFUL_TIMEOUT_S = 8   # seconds to wait before escalating to SIGKILL


def _load_registry() -> dict:
    if _REGISTRY.exists():
        try:
            return json.loads(_REGISTRY.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_registry(data: dict) -> None:
    _REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    _REGISTRY.write_text(json.dumps(data, indent=2), encoding="utf-8")


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


def _terminate_process(pid: int) -> bool:
    """Attempt a graceful termination, escalating to forceful kill if needed.

    Returns True if the process is no longer alive after the attempt.
    """
    if sys.platform == "win32":
        import subprocess
        subprocess.run(["taskkill", "/PID", str(pid)], capture_output=True)
        deadline = time.monotonic() + _GRACEFUL_TIMEOUT_S
        while time.monotonic() < deadline:
            if not _is_process_alive(pid):
                return True
            time.sleep(0.25)
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return True
        deadline = time.monotonic() + _GRACEFUL_TIMEOUT_S
        while time.monotonic() < deadline:
            if not _is_process_alive(pid):
                return True
            time.sleep(0.25)
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    time.sleep(0.5)
    return not _is_process_alive(pid)


def run(name: str) -> None:
    registry = _load_registry()

    if name not in registry:
        display.warn(
            f"Profile '{name}' is not in the registry. "
            "It may have been stopped already or was never started with  majestic run."
        )
        sys.exit(0)

    entry = registry[name]
    pid = entry.get("pid")

    if not pid:
        display.warn(f"No PID recorded for '{name}'. Removing stale registry entry.")
        del registry[name]
        _save_registry(registry)
        sys.exit(0)

    if not _is_process_alive(pid):
        display.warn(
            f"Process {pid} for '{name}' is not running. Cleaning up stale registry entry."
        )
        del registry[name]
        _save_registry(registry)
        sys.exit(0)

    display.info(f"Stopping '{name}' (pid {pid})…")

    success = _terminate_process(pid)

    del registry[name]
    _save_registry(registry)

    if success:
        display.ok(f"Agent '{name}' stopped.")
    else:
        display.err(
            f"Could not confirm that process {pid} terminated. "
            "You may need to kill it manually."
        )
        sys.exit(1)
