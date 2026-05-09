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

from rich.console import Console
from rich.table import Table

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

    if not registry:
        console.print(
            "[dim]No agent daemons are registered.[/dim]\n"
            "Start one with: [bold]majestic run <profile>[/bold]"
        )
        return

    table = Table(
        title="Running Majestic Agents",
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
    )
    table.add_column("Profile", style="bold", min_width=14)
    table.add_column("Name", min_width=14)
    table.add_column("PID", justify="right", min_width=8)
    table.add_column("Port", justify="right", min_width=6)
    table.add_column("Started", min_width=20)
    table.add_column("Status", min_width=14)
    table.add_column("Log", min_width=20)

    stale: list[str] = []

    for profile_name, entry in registry.items():
        pid = entry.get("pid")
        agent_name = entry.get("agent_name", profile_name)
        port = str(entry.get("port", "–"))
        log = entry.get("log", "–")
        started_at = entry.get("started_at", "–")
        # Trim ISO timestamp to human-friendly form if present
        if started_at and started_at != "–" and "T" in started_at:
            started_at = started_at.replace("T", " ")[:19]

        if pid and _is_process_alive(pid):
            status = "[green]running[/green]"
        else:
            status = "[red]dead[/red]"
            stale.append(profile_name)

        table.add_row(
            profile_name,
            agent_name,
            str(pid) if pid else "–",
            port,
            started_at,
            status,
            f"[dim]{log}[/dim]",
        )

    console.print(table)

    if stale:
        console.print(
            f"\n[yellow]Note:[/yellow] {len(stale)} entry/entries appear dead. "
            "They will be cleaned up automatically on next [cyan]majestic stop[/cyan]."
        )
