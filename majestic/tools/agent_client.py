"""
majestic.tools.agent_client
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
HTTP client for delegating tasks to other running Majestic agents.

Agents register themselves in ``data/registry.json`` when they start
(via ``majestic run <name>``).  AgentClient reads that file to discover
live agents and communicates with them over HTTP.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    """Return the repository / project root (three levels above this file)."""
    return Path(__file__).resolve().parent.parent.parent


def _default_registry_path() -> str:
    return str(_project_root() / "data" / "registry.json")


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class AgentClient:
    """Delegate tasks to named running Majestic agents via HTTP.

    Args:
        registry_path: Path to the JSON registry file written by
                       ``majestic run``.  Defaults to ``data/registry.json``
                       relative to the project root.
        timeout:       HTTP request timeout in seconds.
    """

    def __init__(
        self,
        registry_path: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.registry_path = registry_path or _default_registry_path()
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Registry helpers
    # ------------------------------------------------------------------

    def get_registry(self) -> dict[str, Any]:
        """Load and return the running agents registry.

        Returns:
            Dict mapping agent name to its registry entry (port, pid, …).
            Returns an empty dict if the file does not exist or is invalid.
        """
        path = Path(self.registry_path)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def list_available(self) -> list[dict[str, Any]]:
        """Return a list of running agents with their registry information.

        Each entry in the returned list is a dict with at least:
            name  (str)  — agent profile name.
            port  (int)  — HTTP port the agent listens on.
            pid   (int)  — OS process ID.

        Returns:
            List of agent info dicts (may be empty).
        """
        registry = self.get_registry()
        result: list[dict[str, Any]] = []
        for name, info in registry.items():
            entry = dict(info)
            entry["name"] = name
            result.append(entry)
        return result

    def _base_url(self, agent_name: str) -> str:
        """Resolve the base URL for *agent_name* from the registry.

        Args:
            agent_name: Profile name of the target agent.

        Returns:
            Base URL string, e.g. ``"http://localhost:8001"``.

        Raises:
            KeyError: If the agent is not found in the registry.
        """
        registry = self.get_registry()
        if agent_name not in registry:
            available = list(registry.keys())
            raise KeyError(
                f"Agent '{agent_name}' not found in registry. "
                f"Available: {available}"
            )
        port = registry[agent_name]["port"]
        return f"http://localhost:{port}"

    # ------------------------------------------------------------------
    # HTTP actions
    # ------------------------------------------------------------------

    async def delegate(self, agent_name: str, task: str) -> dict[str, Any]:
        """Send a task to a named running agent via ``POST /task``.

        Args:
            agent_name: Profile name of the target agent.
            task:       Natural-language task description.

        Returns:
            dict with keys:
                status  (str)  — ``"accepted"`` on success.
                task_id (str)  — Unique identifier for the submitted task.

        Raises:
            KeyError:  If the agent is not in the registry.
            Exception: On HTTP errors or connection failures.
        """
        import httpx  # deferred import — optional at module level

        base_url = self._base_url(agent_name)
        payload = {"text": task}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{base_url}/task", json=payload)
            response.raise_for_status()
            data = response.json()

        return {
            "status": data.get("status", "accepted"),
            "task_id": data.get("task_id", ""),
            "result": data.get("result", ""),
        }

    async def check_status(self, agent_name: str) -> dict[str, Any]:
        """Perform a health check on a named agent via ``GET /status``.

        Args:
            agent_name: Profile name of the target agent.

        Returns:
            dict with keys returned by the agent's ``/status`` endpoint,
            typically: ``status``, ``agent``, ``port``.

        Raises:
            KeyError:  If the agent is not in the registry.
            Exception: On HTTP errors or connection failures.
        """
        import httpx  # deferred import

        base_url = self._base_url(agent_name)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{base_url}/status")
            response.raise_for_status()
            return response.json()

    # ------------------------------------------------------------------
    # LLM tool schema
    # ------------------------------------------------------------------

    def tool_schema(self) -> dict[str, Any]:
        """Return a JSON schema descriptor for use in LLM tool calls.

        Returns:
            OpenAI-compatible tool schema dict.
        """
        return {
            "name": "agent_client",
            "description": "Delegate a task to another running Majestic agent",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_name": {
                        "type": "string",
                        "description": "Name of the target agent (must be running)",
                    },
                    "task": {
                        "type": "string",
                        "description": "Task description to send to the agent",
                    },
                },
                "required": ["agent_name", "task"],
            },
        }
