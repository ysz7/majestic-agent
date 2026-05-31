"""
majestic.config.settings
~~~~~~~~~~~~~~~~~~~~~~~~
Profile-based configuration loader.

Priority order for any setting:
  1. Profile .env   (profiles/<name>/.env)
  2. Root .env      (.env at project root)
  3. Process environment (os.environ)
  4. Hardcoded defaults

Model routing can be defined globally in the root .env so you don't have to
repeat it in every profile:

    MAJESTIC_MODEL_REASON=anthropic/claude-sonnet-4-5
    MAJESTIC_MODEL_SIMPLE=meta-llama/llama-3.1-8b-instruct:free
    MAJESTIC_MODEL_CODE=qwen/qwen-2.5-coder-32b-instruct
    MAJESTIC_MODEL_REFLECTION=meta-llama/llama-3.1-8b-instruct:free

Per-profile persona.yaml `model_routing:` section overrides these globals.

Ollama (local models):
    OLLAMA_BASE_URL=http://localhost:11434   (default)
    OLLAMA_MODEL=llama3.2                   (default fallback model)
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


def _load_root_env() -> dict[str, str | None]:
    """Load the project-root .env as a global baseline (lowest priority)."""
    root_env = _project_root() / ".env"
    if root_env.exists():
        return dotenv_values(root_env)
    return {}


# Global defaults for model routing (used when no profile/env override exists)
_DEFAULT_MODELS: dict[str, str] = {
    "reason":     "anthropic/claude-sonnet-4-5",
    "simple":     "meta-llama/llama-3.1-8b-instruct:free",
    "code":       "qwen/qwen-2.5-coder-32b-instruct",
    "reflection": "meta-llama/llama-3.1-8b-instruct:free",
}

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class Settings:
    """Loads and exposes configuration for a single named profile."""

    def __init__(self, profile_name: str = "default") -> None:
        self._profile_name = profile_name
        self._profile_dir = _profiles_root() / profile_name
        self._layout_migrated = False

        if not self._profile_dir.exists():
            raise FileNotFoundError(
                f"Profile '{profile_name}' not found.\n"
                f"Run  majestic new {profile_name}  to create it, "
                "or  majestic setup  for first-time configuration."
            )

        # Priority 1: root .env (global baseline)
        self._root_env: dict[str, str | None] = _load_root_env()

        # Priority 2: profile .env (overrides root)
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
        d = self._profile_dir / "workspace"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def data_dir(self) -> Path:
        d = self._profile_dir / "data"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def db_path(self, name: str) -> str:
        """Absolute path to a profile SQLite DB by logical name (e.g. ``"research"``).

        DBs are organized into tier subfolders (``runtime/`` · ``memory/`` ·
        ``intel/``). On first call, existing flat ``data/<name>.db`` files are
        migrated into their tier automatically (one-time, idempotent). If a flat
        file still exists for *name* (migration skipped/failed), the flat path is
        returned so accumulated data is never stranded behind an empty new DB.
        """
        from majestic.storage.migrate import DB_TIERS, migrate_layout

        if not self._layout_migrated:
            self._layout_migrated = True
            migrate_layout(self.data_dir)

        tier = DB_TIERS.get(name)
        if tier is None:
            return str(self.data_dir / f"{name}.db")

        flat = self.data_dir / f"{name}.db"
        tiered_dir = self.data_dir / tier
        tiered = tiered_dir / f"{name}.db"
        if flat.exists() and not tiered.exists():
            return str(flat)  # don't strand un-migrated data
        tiered_dir.mkdir(parents=True, exist_ok=True)
        return str(tiered)

    @property
    def db_backend(self) -> str:
        """Storage backend name (``MAJESTIC_DB_BACKEND``, default ``"sqlite"``).

        Selects the :class:`StorageBackend` implementation via
        ``majestic.storage.backends.get_backend``. Only ``"sqlite"`` is wired
        today; other values raise until their adapter is added.
        """
        return (self._env_get("MAJESTIC_DB_BACKEND", "sqlite") or "sqlite").strip().lower()

    @property
    def skills_dir(self) -> Path:
        d = self._profile_dir / "skills"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def shared_skills_dir(self) -> Path:
        """Global shared skills library at profiles/shared/skills/ — available to all profiles."""
        return _profiles_root() / "shared" / "skills"

    @property
    def output_dir(self) -> Path:
        d = self._profile_dir / "workspace" / "output"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def tools_dir(self) -> Path:
        d = self._profile_dir / "workspace" / "tools"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def temp_dir(self) -> Path:
        d = self._profile_dir / "workspace" / "temp"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------
    # Env lookup: profile .env → root .env → os.environ → default
    # ------------------------------------------------------------------

    def _env_get(self, key: str, default: str | None = None) -> str | None:
        # Profile .env is highest priority
        if key in self._env and self._env[key] is not None:
            return self._env[key]
        # Root .env next
        if key in self._root_env and self._root_env[key] is not None:
            return self._root_env[key]
        # OS environment
        val = os.environ.get(key)
        if val is not None:
            return val
        return default

    # ------------------------------------------------------------------
    # API keys
    # ------------------------------------------------------------------

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

    # Ollama — no key needed, just a base URL
    @property
    def ollama_base_url(self) -> str | None:
        return self._env_get("OLLAMA_BASE_URL")

    @property
    def ollama_model(self) -> str | None:
        return self._env_get("OLLAMA_MODEL")

    @property
    def agent_port(self) -> int:
        # persona.yaml port takes precedence over env var
        persona_port = self._persona.get("port")
        if persona_port is not None:
            try:
                return int(persona_port)
            except (TypeError, ValueError):
                pass
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
        """Returns the single configured model for all step types."""
        model = self.get_model()
        return {
            "reason":     model,
            "simple":     model,
            "code":       model,
            "reflection": model,
        }

    @property
    def limits(self) -> dict[str, Any]:
        raw = self._persona.get("limits", {})
        if isinstance(raw, dict):
            return dict(raw)
        return {}

    @property
    def streaming(self) -> bool:
        """False by default. Enable via persona.yaml: `streaming: true`."""
        return bool(self._persona.get("streaming", False))

    @property
    def working_persistent(self) -> bool:
        """True if persona.yaml has `memory.working_persistent: true`."""
        memory_cfg = self._persona.get("memory", {})
        if isinstance(memory_cfg, dict):
            return bool(memory_cfg.get("working_persistent", True))
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def validate(self) -> None:
        """Raise ValueError if no LLM provider is configured."""
        has_cloud = any([
            self.openrouter_api_key,
            self.anthropic_api_key,
            self.openai_api_key,
        ])
        has_local = bool(self.ollama_base_url)

        if not has_cloud and not has_local:
            raise ValueError(
                "No LLM provider configured for profile '{}'.\n\n"
                "Option A — Cloud (add to .env):\n"
                "  OPENROUTER_API_KEY=sk-or-...   (recommended, access to 200+ models)\n"
                "  ANTHROPIC_API_KEY=sk-ant-...   (or Anthropic directly)\n"
                "  OPENAI_API_KEY=sk-...          (or OpenAI directly)\n\n"
                "Option B — Local Ollama (no API key needed):\n"
                "  1. Install: https://ollama.com\n"
                "  2. Run: ollama pull llama3.2 && ollama serve\n"
                "  3. Add to .env: OLLAMA_BASE_URL=http://localhost:11434\n\n"
                "Put keys in .env (project root) to share across all profiles.".format(
                    self._profile_name
                )
            )

    def get_model(self, step_type: str = "reason") -> str:
        """Return the single configured model (step_type is ignored)."""
        ollama_only = self.ollama_base_url and not any([
            self.openrouter_api_key,
            self.anthropic_api_key,
            self.openai_api_key,
        ])
        if ollama_only:
            return self.ollama_model or "llama3.2"

        return (
            self._env_get("MAJESTIC_MODEL_REASON")
            or self._env_get("MAJESTIC_MODEL")
            or _DEFAULT_MODELS["reason"]
        )

    # ------------------------------------------------------------------
    # Class-level helpers
    # ------------------------------------------------------------------

    @classmethod
    def list_profiles(cls) -> list[str]:
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
        return (_profiles_root() / name).is_dir()

    def __repr__(self) -> str:
        return (
            f"Settings(profile={self._profile_name!r}, "
            f"name={self.agent_name!r}, port={self.agent_port})"
        )
