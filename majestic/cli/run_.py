"""
majestic.cli.run_
~~~~~~~~~~~~~~~~~
Start an agent profile as a detached background daemon.

The daemon process runs `majestic <name>` (i.e. the foreground runner) in a
subprocess that is detached from the current terminal.  The process id is
stored in data/registry.json so that `majestic ps` and `majestic stop` can
manage it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

from majestic.config.settings import Settings

console = Console()

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_REGISTRY = _PROJECT_ROOT / "data" / "registry.json"


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
    """Return True if a process with the given PID is currently running."""
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


def run(name: str) -> None:
    if not Settings.profile_exists(name):
        console.print(
            f"[red]Error:[/red] Profile '{name}' does not exist.\n"
            f"Create it with: [bold]majestic new {name}[/bold]"
        )
        sys.exit(1)

    # Validate config before spawning
    try:
        settings = Settings(name)
        settings.validate()
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    # Check if already running
    registry = _load_registry()
    entry = registry.get(name, {})
    existing_pid = entry.get("pid")
    if existing_pid and _is_process_alive(existing_pid):
        console.print(
            f"[yellow]Warning:[/yellow] Profile '{name}' is already running "
            f"(pid {existing_pid}).\n"
            f"Stop it first with: [bold]majestic stop {name}[/bold]"
        )
        sys.exit(0)

    # Resolve the python interpreter from the current environment
    python = sys.executable

    # Spawn: python -m majestic <name>  — foreground runner handles the loop
    cmd = [python, "-m", "majestic", name]

    # Log file for daemon output
    log_dir = _PROJECT_ROOT / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{name}.log"

    with open(log_file, "a", encoding="utf-8") as log_fh:
        if sys.platform == "win32":
            # On Windows use DETACHED_PROCESS flag
            DETACHED_PROCESS = 0x00000008
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            proc = subprocess.Popen(
                cmd,
                stdout=log_fh,
                stderr=log_fh,
                stdin=subprocess.DEVNULL,
                creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                cwd=str(_PROJECT_ROOT),
            )
        else:
            proc = subprocess.Popen(
                cmd,
                stdout=log_fh,
                stderr=log_fh,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                cwd=str(_PROJECT_ROOT),
            )

    pid = proc.pid
    registry[name] = {
        "pid": pid,
        "profile": name,
        "agent_name": settings.agent_name,
        "port": settings.agent_port,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "log": str(log_file),
    }
    _save_registry(registry)

    console.print(
        f"[green]✓[/green] Agent '{settings.agent_name}' (profile: {name}) "
        f"started in background.\n"
        f"  PID: [bold]{pid}[/bold]\n"
        f"  Port: [bold]{settings.agent_port}[/bold]\n"
        f"  Logs: [dim]{log_file}[/dim]\n\n"
        f"Use [cyan]majestic ps[/cyan] to check status or "
        f"[cyan]majestic stop {name}[/cyan] to stop it."
    )
