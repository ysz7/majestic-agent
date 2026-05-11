"""
Startup checks and initialization for the Majestic agent framework.

Validates configuration, ensures required directories and databases exist,
recovers incomplete checkpoints, and schedules the janitor if overdue.
"""

import json
import logging
import os
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


class StartupError(RuntimeError):
    """Raised when a fatal startup check fails."""


class StartupManager:
    """Orchestrates all startup checks and initialization steps.

    Args:
        settings: A settings object (or dict-like) that exposes at minimum:
            - ``base_dir``  – root directory of the agent workspace
            - ``data_dir``  – directory for persistent data files
            - ``temp_dir``  – directory for temporary files
            - ``env_file``  – path to the ``.env`` file (str or Path)
            - ``persona_file`` – path to ``persona.yaml`` (str or Path)
            - ``databases``  – mapping of logical name → SQLite file path
            - ``checkpoint_dir`` – directory where checkpoint files are stored
    """

    # Required top-level keys inside persona.yaml (validated as YAML keys
    # using a lightweight parse — no external dependency needed).
    _REQUIRED_PERSONA_KEYS = {"name", "role"}

    # No specific env var is required — any provider is accepted.
    # LLM key validation is done by Settings.validate() before startup runs.
    _REQUIRED_ENV_VARS: set[str] = set()

    def __init__(self, settings) -> None:
        self.settings = settings

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def run(self) -> list[dict]:
        """Run all startup checks and initialization in order.

        Returns:
            List of incomplete checkpoint dicts (may be empty).  Each dict has
            ``task_id``, ``started_at``, ``status``, and ``file`` keys so the
            caller can offer the user a resume prompt.

        Raises:
            StartupError: if a fatal check fails (missing files, invalid
                          configuration, etc.).
        """
        logger.info("Running startup checks …")
        self._validate_settings()
        self._ensure_dirs()
        self._init_databases()
        incomplete = await self._recover_checkpoints()
        self._schedule_janitor()
        logger.info("Startup complete.")
        return incomplete

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _validate_settings(self) -> None:
        """Validate that persona.yaml exists and has required keys.

        Profile .env is optional — keys may come from the root .env.
        LLM provider validation is handled by Settings.validate() before startup.
        """
        # Resolve persona.yaml path: prefer settings.profile_dir, then fallback
        profile_dir = getattr(self.settings, "profile_dir", None)
        if profile_dir is not None:
            persona_path = Path(profile_dir) / "persona.yaml"
        else:
            persona_path = Path(self._get("persona_file", "persona.yaml"))

        if not persona_path.exists():
            raise StartupError(
                f"Missing persona.yaml at '{persona_path}'. "
                "Create it to define the agent's identity."
            )

        persona_keys = self._parse_yaml_keys(persona_path)
        missing_keys = self._REQUIRED_PERSONA_KEYS - persona_keys
        if missing_keys:
            raise StartupError(
                f"persona.yaml is missing required key(s): "
                f"{', '.join(sorted(missing_keys))}"
            )

        logger.debug("Settings validation passed.")

    def _ensure_dirs(self) -> None:
        """Create workspace and data directories if they do not exist."""
        # Prefer Settings properties (profile_dir-relative); fall back to dict keys.
        profile_dir = getattr(self.settings, "profile_dir", None)
        if profile_dir is not None:
            dirs = [
                Path(profile_dir) / "workspace",
                Path(profile_dir) / "workspace" / "temp",
                Path(profile_dir) / "data",
                Path(profile_dir) / "data" / "checkpoints",
            ]
        else:
            dirs = [
                Path(self._get("base_dir", "workspace")),
                Path(self._get("data_dir", "data")),
                Path(self._get("temp_dir", os.path.join("workspace", "temp"))),
                Path(self._get("checkpoint_dir", os.path.join("data", "checkpoints"))),
            ]
        for path in dirs:
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
                logger.info("Created directory: %s", path)
            else:
                logger.debug("Directory exists: %s", path)

    def _init_databases(self) -> None:
        """Initialize SQLite databases by ensuring their files exist.

        The databases mapping may contain any number of entries.  Each value
        is interpreted as a file path relative to the working directory (or
        absolute).  An empty SQLite database file is created on first access
        simply by opening a connection and closing it immediately.
        """
        profile_dir = getattr(self.settings, "profile_dir", None)
        if profile_dir is not None:
            data_dir = Path(profile_dir) / "data"
            databases = {
                "episodic": data_dir / "episodic.db",
                "checkpoints": data_dir / "checkpoints.db",
            }
        else:
            databases = {
                k: Path(v) for k, v in self._get("databases", {
                    "episodic": os.path.join("data", "episodic.db"),
                    "checkpoints": os.path.join("data", "checkpoints.db"),
                }).items()
            }

        for name, db_path in databases.items():
            path = Path(db_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                conn = sqlite3.connect(str(path))
                conn.close()
                logger.info("Initialized database '%s' at %s", name, path)
            else:
                logger.debug("Database '%s' already exists at %s", name, path)

    async def _recover_checkpoints(self) -> list[dict]:
        """Detect incomplete checkpoints and return them to the caller.

        A checkpoint is *incomplete* if its ``status`` field is absent or not
        ``"completed"`` / ``"failed"``.  The caller (main loop) decides whether
        to offer the user a resume prompt.

        Returns:
            List of dicts with keys: task_id, started_at, status, file.
        """
        profile_dir = getattr(self.settings, "profile_dir", None)
        if profile_dir is not None:
            checkpoint_dir = Path(profile_dir) / "data" / "checkpoints"
        else:
            checkpoint_dir = Path(
                self._get("checkpoint_dir", os.path.join("data", "checkpoints"))
            )
        if not checkpoint_dir.exists():
            return []

        incomplete: list[dict] = []
        for cp_file in sorted(checkpoint_dir.glob("*.json")):
            try:
                data = json.loads(cp_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Could not read checkpoint file %s: %s", cp_file, exc)
                continue

            status = data.get("status", "unknown")
            if status not in ("completed", "failed"):
                entry = {
                    "task_id": data.get("task_id", cp_file.stem),
                    "started_at": data.get("started_at", "unknown"),
                    "status": status,
                    "file": str(cp_file),
                }
                incomplete.append(entry)
                logger.warning(
                    "Incomplete checkpoint: task_id=%s  started=%s  file=%s",
                    entry["task_id"],
                    entry["started_at"],
                    cp_file.name,
                )

        if incomplete:
            logger.warning(
                "%d incomplete task(s) found — pass task_id to AgentRuntime.run() "
                "to resume from the last saved step.",
                len(incomplete),
            )
        else:
            logger.debug("No incomplete checkpoints found.")

        return incomplete

    def _schedule_janitor(self) -> None:
        """Schedule the janitor if it has not run in the last 24 hours.

        Imports :class:`~majestic.system.janitor.Janitor` lazily to avoid
        circular imports and runs it synchronously in the same process.
        The janitor writes its own timestamp file so this method can check
        whether it is overdue without tracking additional state.
        """
        from majestic.system.janitor import Janitor  # lazy import

        janitor = Janitor(self.settings)
        if janitor.should_run():
            logger.info("Janitor is overdue — running cleanup now.")
            try:
                janitor.run()
            except Exception as exc:  # pylint: disable=broad-except
                # Janitor failures are non-fatal; log and continue.
                logger.warning("Janitor run failed (non-fatal): %s", exc)
        else:
            logger.debug("Janitor ran recently; skipping.")

    # ------------------------------------------------------------------
    # Internal utilities
    # ------------------------------------------------------------------

    def _get(self, key: str, default=None):
        """Retrieve a value from settings, supporting both dict and object APIs."""
        if isinstance(self.settings, dict):
            return self.settings.get(key, default)
        return getattr(self.settings, key, default)

    @staticmethod
    def _parse_dotenv(path: Path) -> dict:
        """Parse a ``.env`` file into a ``{key: value}`` dict.

        Only lines of the form ``KEY=VALUE`` (ignoring comments and blanks)
        are returned.  Inline comments after the value are stripped.
        Quoted values have their surrounding quotes removed.
        """
        result: dict[str, str] = {}
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, rest = line.partition("=")
            key = key.strip()
            # Strip inline comments (# preceded by space).
            value = rest.split(" #")[0].strip()
            # Strip surrounding quotes (single or double).
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            result[key] = value
        return result

    @staticmethod
    def _parse_yaml_keys(path: Path) -> set:
        """Extract top-level mapping keys from a YAML file without PyYAML.

        Only lines whose first non-whitespace character is a plain-text
        word character followed by a colon are considered top-level keys
        (indented lines are skipped).  This is sufficient for validating
        simple persona files.
        """
        keys: set[str] = set()
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            if not raw_line or raw_line[0] in (" ", "\t", "#", "-", "[", "{"):
                continue
            if ":" in raw_line:
                key = raw_line.split(":")[0].strip()
                if key:
                    keys.add(key)
        return keys
