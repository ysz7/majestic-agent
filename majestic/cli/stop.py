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

from rich.console import Console

console = Console()

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
        # Windows: taskkill first (graceful), then /F (forceful)
        import subprocess
        subprocess.run(
            ["taskkill", "/PID", str(pid)],
            capture_output=True,
        )
        deadline = time.monotonic() + _GRACEFUL_TIMEOUT_S
        while time.monotonic() < deadline:
            if not _is_process_alive(pid):
                return True
            time.sleep(0.25)
        # Forceful
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return True  # already gone
        deadline = time.monotonic() + _GRACEFUL_TIMEOUT_S
        while time.monotonic() < deadline:
            if not _is_process_alive(pid):
                return True
            time.sleep(0.25)
        # Escalate
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    # Final check
    time.sleep(0.5)
    return not _is_process_alive(pid)


def run(name: str) -> None:
    registry = _load_registry()

    if name not in registry:
        console.print(
            f"[yellow]Warning:[/yellow] Profile '{name}' is not in the registry.\n"
            "It may have been stopped already or was never started with "
            "[bold]majestic run[/bold]."
        )
        sys.exit(0)

    entry = registry[name]
    pid = entry.get("pid")

    if not pid:
        console.print(
            f"[yellow]Warning:[/yellow] No PID recorded for '{name}'. "
            "Removing stale registry entry."
        )
        del registry[name]
        _save_registry(registry)
        sys.exit(0)

    if not _is_process_alive(pid):
        console.print(
            f"[yellow]Warning:[/yellow] Process {pid} for '{name}' is not running. "
            "Cleaning up stale registry entry."
        )
        del registry[name]
        _save_registry(registry)
        sys.exit(0)

    console.print(f"Stopping '{name}' (pid {pid}) …")

    success = _terminate_process(pid)

    # Remove from registry regardless (we don't want stale entries)
    del registry[name]
    _save_registry(registry)

    if success:
        console.print(f"[green]✓[/green] Agent '{name}' stopped.")
    else:
        console.print(
            f"[red]Warning:[/red] Could not confirm that process {pid} terminated.\n"
            "You may need to kill it manually."
        )
        sys.exit(1)
