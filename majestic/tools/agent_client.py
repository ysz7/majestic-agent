"""
majestic.tools.agent_client
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
HTTP client for delegating tasks to other running Majestic agents.

Agents register themselves in ``data/registry.json`` when they start.
AgentClient reads that file to discover live agents and communicates with
them over HTTP.  Use ``ensure_running()`` to auto-start an agent before
delegating — the agent will be spawned as a background daemon if it is
not already running.
"""

from __future__ import annotations

import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _get_agent_token() -> str:
    token_path = _project_root() / "data" / "agent_token"
    if token_path.exists():
        return token_path.read_text(encoding="utf-8").strip()
    return ""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class AgentClient:
    """Delegate tasks to named Majestic agents via HTTP.

    Supports auto-starting agents that are not yet running via
    ``ensure_running()``.
    """

    def __init__(self, timeout: float = 60.0) -> None:
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Registry helpers
    # ------------------------------------------------------------------

    def get_registry(self) -> dict[str, Any]:
        from majestic.cli.registry_db import load_registry
        return load_registry()

    def _save_registry(self, data: dict) -> None:
        from majestic.cli.registry_db import save_entry
        for profile, entry in data.items():
            save_entry(profile, entry)

    def list_available(self) -> list[dict[str, Any]]:
        registry = self.get_registry()
        result: list[dict[str, Any]] = []
        for name, info in registry.items():
            entry = dict(info)
            entry["name"] = name
            result.append(entry)
        return result

    def list_profiles_with_roles(self) -> list[dict[str, Any]]:
        """Return ALL agent profiles with role info and running status.

        Scans ``profiles/`` and enriches each entry with data from
        ``persona.yaml``.  Useful for the LLM to decide which agent to
        delegate a task to.

        Returns:
            List of dicts with keys: profile, name, role, running, port.
        """
        import yaml

        profiles_dir = _project_root() / "profiles"
        registry = self.get_registry()
        result: list[dict[str, Any]] = []

        if not profiles_dir.exists():
            return result

        for entry in sorted(profiles_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue

            persona: dict[str, Any] = {}
            persona_file = entry / "persona.yaml"
            if persona_file.exists():
                try:
                    persona = yaml.safe_load(
                        persona_file.read_text(encoding="utf-8")
                    ) or {}
                except Exception:
                    pass

            running_info = registry.get(entry.name, {})
            result.append({
                "profile": entry.name,
                "name": persona.get("name", entry.name),
                "role": persona.get("role", "General assistant"),
                "running": bool(running_info),
                "port": running_info.get("port") or persona.get("port"),
            })

        return result

    def _base_url(self, agent_name: str) -> str:
        registry = self.get_registry()
        if agent_name not in registry:
            raise KeyError(
                f"Agent '{agent_name}' not found in registry. "
                f"Available: {list(registry.keys())}"
            )
        port = registry[agent_name]["port"]
        return f"http://localhost:{port}"

    # ------------------------------------------------------------------
    # Auto-start
    # ------------------------------------------------------------------

    async def ensure_running(self, profile_name: str, timeout: float = 20.0) -> None:
        """Ensure *profile_name* is running, spawning it as a daemon if not.

        Steps:
        1. Check registry — if present, probe the port with GET /status.
        2. If healthy → return immediately.
        3. Otherwise spawn ``majestic.__background__ <profile_name>`` and
           poll until the HTTP server is ready.

        Args:
            profile_name: Profile directory name under ``profiles/``.
            timeout:      Seconds to wait for the agent to become ready.

        Raises:
            ValueError:   Profile does not exist.
            TimeoutError: Agent did not become ready within *timeout* seconds.
        """
        import asyncio
        import httpx
        from majestic.config.settings import Settings

        root = _project_root()

        # ── 1. Check if already healthy ──────────────────────────────────
        registry = self.get_registry()
        if profile_name in registry:
            port = registry[profile_name].get("port", 8000)
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    r = await client.get(f"http://localhost:{port}/status")
                    if r.status_code == 200:
                        return
            except Exception:
                pass  # stale entry — fall through to respawn

        # ── 2. Validate profile ───────────────────────────────────────────
        if not Settings.profile_exists(profile_name):
            raise ValueError(
                f"Profile '{profile_name}' does not exist. "
                f"Create it with: majestic new {profile_name}"
            )

        settings = Settings(profile_name)
        port = settings.agent_port

        # ── 3. Spawn daemon ───────────────────────────────────────────────
        cmd = [sys.executable, "-m", "majestic.__background__", profile_name]

        log_dir = root / "data" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{profile_name}.log"

        with open(log_file, "a", encoding="utf-8") as log_fh:
            if sys.platform == "win32":
                proc = subprocess.Popen(
                    cmd,
                    stdout=log_fh, stderr=log_fh, stdin=subprocess.DEVNULL,
                    creationflags=0x00000200 | 0x08000000,  # NEW_PROCESS_GROUP | NO_WINDOW
                    cwd=str(root),
                )
            else:
                proc = subprocess.Popen(
                    cmd,
                    stdout=log_fh, stderr=log_fh, stdin=subprocess.DEVNULL,
                    start_new_session=True,
                    cwd=str(root),
                )

        # Write initial registry entry so other tools see it immediately
        from majestic.cli.registry_db import save_entry
        save_entry(profile_name, {
            "pid": proc.pid,
            "profile": profile_name,
            "agent_name": settings.agent_name,
            "port": port,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "log": str(log_file),
            "status": "starting",
        })

        # ── 4. Poll until ready ───────────────────────────────────────────
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout

        while loop.time() < deadline:
            await asyncio.sleep(1.0)
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    r = await client.get(f"http://localhost:{port}/status")
                    if r.status_code == 200:
                        return
            except Exception:
                pass

        raise TimeoutError(
            f"Agent '{profile_name}' did not become ready within {timeout:.0f}s. "
            f"Check logs: {log_file}"
        )

    # ------------------------------------------------------------------
    # HTTP actions
    # ------------------------------------------------------------------

    async def delegate(self, agent_name: str, task: str) -> dict[str, Any]:
        """Send a task to a named agent via ``POST /task``.

        The agent must already be running.  Use the ``delegate_to_agent``
        tool (registered in foreground.py) which calls ``ensure_running``
        automatically.
        """
        import httpx

        base_url = self._base_url(agent_name)
        payload = {"text": task}

        headers = {"X-Agent-Token": _get_agent_token()}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{base_url}/task", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        return {
            "status": data.get("status", "accepted"),
            "task_id": data.get("task_id", ""),
            "result": data.get("result", ""),
        }

    async def check_status(self, agent_name: str) -> dict[str, Any]:
        import httpx

        base_url = self._base_url(agent_name)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{base_url}/status")
            response.raise_for_status()
            return response.json()

    # ------------------------------------------------------------------
    # LLM tool schemas
    # ------------------------------------------------------------------

    def tool_schema(self) -> dict[str, Any]:
        return {
            "name": "delegate_to_agent",
            "description": (
                "Delegate a task to a specialized agent. "
                "The agent will be auto-started if not already running. "
                "Use list_agents first to discover available agents and their roles."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_name": {
                        "type": "string",
                        "description": "Profile name of the target agent (e.g. 'pain_hunter')",
                    },
                    "task": {
                        "type": "string",
                        "description": "Natural-language task description to send to the agent",
                    },
                },
                "required": ["agent_name", "task"],
            },
        }

    def list_agents_schema(self) -> dict[str, Any]:
        return {
            "name": "list_agents",
            "description": (
                "List all available agent profiles with their roles and running status. "
                "Use this to find the right specialized agent for a task before delegating."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        }
