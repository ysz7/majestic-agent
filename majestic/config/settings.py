"""
majestic.config.settings
~~~~~~~~~~~~~~~~~~~~~~~~
Profile-based configuration loader.

Each profile lives under  profiles/<profile_name>/  and contains:
  .env          — secrets and environment-level overrides
  persona.yaml  — agent personality, model routing, and limits

Usage::

    from majestic.config.settings import Settings

    s = Settings("sales_agent")
    s.validate()
    model = s.get_model("reason")
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    """Return the repository / project root (two levels above this file)."""
    return Path(__file__).resolve().parent.parent.parent


def _profiles_root() -> Path:
    return _project_root() / "profiles"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class Settings:
    """Loads and exposes configuration for a single named profile."""

    def __init__(self, profile_name: str = "default") -> None:
        self._profile_name = profile_name
        self._profile_dir = _profiles_root() / profile_name

        if not self._profile_dir.exists():
            raise FileNotFoundError(
                f"Profile directory not found: {self._profile_dir}\n"
                f"Run  majestic new {profile_name}  to create it."
            )

        # Load .env (profile-level overrides take priority over the process env)
        env_file = self._profile_dir / ".env"
        self._env: dict[str, str | None] = (
            dotenv_values(env_file) if env_file.exists() else {}
        )

        # Load persona.yaml
        persona_file = self._profile_dir / "persona.yaml"
        if persona_file.exists():
            with persona_file.open("r", encoding="utf-8") as fh:
                self._persona: dict[str, Any] = yaml.safe_load(fh) or {}
        else:
            self._persona = {}

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def profile_name(self) -> str:
        return self._profile_name

    @property
    def profile_dir(self) -> Path:
        return self._profile_dir

    # ------------------------------------------------------------------
    # Derived directories
    # ------------------------------------------------------------------

    @property
    def workspace_dir(self) -> Path:
        """Sandboxed working directory for this agent's file operations."""
        d = self._profile_dir / "workspace"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def data_dir(self) -> Path:
        """Persistent data directory (vector DB, memory store, caches, …)."""
        d = self._profile_dir / "data"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def skills_dir(self) -> Path:
        """Directory for profile-specific skill/plugin scripts."""
        d = self._profile_dir / "skills"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------
    # API keys — prefer profile .env, fall back to process environment
    # ------------------------------------------------------------------

    def _env_get(self, key: str, default: str | None = None) -> str | None:
        value = self._env.get(key)
        if value is None:
            value = os.environ.get(key)
        return value if value is not None else default

    @property
    def openrouter_api_key(self) -> str | None:
        return self._env_get("OPENROUTER_API_KEY")

    @property
    def anthropic_api_key(self) -> str | None:
        return self._env_get("ANTHROPIC_API_KEY")

    @property
    def openai_api_key(self) -> str | None:
        return self._env_get("OPENAI_API_KEY")

    @property
    def brave_search_api_key(self) -> str | None:
        return self._env_get("BRAVE_SEARCH_API_KEY")

    @property
    def agent_port(self) -> int:
        raw = self._env_get("AGENT_PORT", "8000")
        try:
            return int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 8000

    # ------------------------------------------------------------------
    # Persona fields
    # ------------------------------------------------------------------

    @property
    def agent_name(self) -> str:
        return str(self._persona.get("name", "Assistant"))

    @property
    def agent_role(self) -> str:
        return str(self._persona.get("role", "General purpose AI assistant"))

    @property
    def agent_tone(self) -> str:
        return str(self._persona.get("tone", "helpful, concise"))

    @property
    def agent_language(self) -> str:
        return str(self._persona.get("language", "en"))

    @property
    def agent_restrictions(self) -> list[str]:
        raw = self._persona.get("restrictions", [])
        if isinstance(raw, list):
            return [str(r) for r in raw]
        return []

    @property
    def agent_context(self) -> str:
        return str(self._persona.get("context", ""))

    @property
    def model_routing(self) -> dict[str, str]:
        raw = self._persona.get("model_routing", {})
        if isinstance(raw, dict):
            return {str(k): str(v) for k, v in raw.items()}
        return {}

    @property
    def limits(self) -> dict[str, Any]:
        raw = self._persona.get("limits", {})
        if isinstance(raw, dict):
            return dict(raw)
        return {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def validate(self) -> None:
        """Raise ValueError if no LLM API key is configured."""
        keys = [
            self.openrouter_api_key,
            self.anthropic_api_key,
            self.openai_api_key,
        ]
        if not any(keys):
            raise ValueError(
                f"Profile '{self._profile_name}' has no LLM API key configured.\n"
                "Set at least one of OPENROUTER_API_KEY, ANTHROPIC_API_KEY, or "
                "OPENAI_API_KEY in your profile's .env file."
            )

    def get_model(self, step_type: str) -> str:
        """Return the model name for the given step type.

        Args:
            step_type: One of 'reason', 'simple', 'code', 'reflection',
                       or any key defined in model_routing.

        Returns:
            Model identifier string.  Falls back to the 'reason' model if the
            requested step_type is not found, then to a hard-coded default.
        """
        routing = self.model_routing
        if step_type in routing:
            return routing[step_type]
        # Fallback chain: reason → first available → hard-coded
        if "reason" in routing:
            return routing["reason"]
        if routing:
            return next(iter(routing.values()))
        return "anthropic/claude-sonnet-4-5"

    # ------------------------------------------------------------------
    # Class-level helpers
    # ------------------------------------------------------------------

    @classmethod
    def list_profiles(cls) -> list[str]:
        """Return a sorted list of profile names found in profiles/."""
        root = _profiles_root()
        if not root.exists():
            return []
        return sorted(
            entry.name
            for entry in root.iterdir()
            if entry.is_dir() and not entry.name.startswith(".")
        )

    @classmethod
    def profile_exists(cls, name: str) -> bool:
        """Return True if a profile directory named *name* exists."""
        return (_profiles_root() / name).is_dir()

    # ------------------------------------------------------------------
    # repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"Settings(profile={self._profile_name!r}, "
            f"name={self.agent_name!r}, port={self.agent_port})"
        )
