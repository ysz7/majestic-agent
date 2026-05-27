import logging
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_SKILL_DEPTH = 3


class ProceduralMemory:
    """Loads YAML skill files from profile's skills/ directory. Hot-reloads on change.

    Supports skill composition: a step can be a plain string or a dict
    ``{skill: other_skill_name, input: "optional context"}`` to embed another
    skill's steps inline (max nesting depth = 3, cycle-safe).

    If ``shared_dir`` is provided, shared skills are loaded first (lower priority)
    and profile skills override them.
    """

    def __init__(self, skills_dir: str, shared_dir: str | None = None):
        self.skills_dir = Path(skills_dir)
        self.shared_dir = Path(shared_dir) if shared_dir else None
        self._skills: dict[str, dict] = {}
        self._last_modified: dict[str, float] = {}
        self._priorities: dict[str, float] = {}
        self.reload()

    def reload(self):
        """Scan skills directories and load/reload any changed YAML files."""
        # Shared skills first (lower priority — profile skills override)
        if self.shared_dir and self.shared_dir.exists():
            self._load_dir(self.shared_dir)

        # Profile-specific skills (higher priority)
        if self.skills_dir.exists():
            self._load_dir(self.skills_dir)

        self._deduplicate_triggers()

    def _load_dir(self, directory: Path) -> None:
        for path in sorted(directory.glob("*.yaml")):
            mtime = path.stat().st_mtime
            key = str(path)
            if key not in self._last_modified or self._last_modified[key] < mtime:
                try:
                    with open(path, encoding="utf-8") as f:
                        skill = yaml.safe_load(f)
                    if not isinstance(skill, dict):
                        continue
                    name = skill.get("name") or path.stem
                    self._skills[name] = skill
                    self._last_modified[key] = mtime
                except Exception as exc:
                    logger.warning("Failed to load skill %s: %s", path.name, exc)

    def _deduplicate_triggers(self) -> None:
        claimed: dict[str, str] = {}
        for name in sorted(self._skills):
            skill = self._skills[name]
            deduped = []
            for trigger in skill.get("triggers", []):
                key = trigger.lower()
                if key in claimed:
                    logger.warning(
                        "Skill '%s' trigger '%s' already claimed by '%s' — skipped",
                        name, trigger, claimed[key],
                    )
                else:
                    claimed[key] = name
                    deduped.append(trigger)
            skill["triggers"] = deduped

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_all(self) -> list[dict]:
        self.reload()
        return list(self._skills.values())

    def boost_priority(self, skill_name: str, amount: float = 1.0) -> None:
        """Increase runtime priority for a skill (session-local, not persisted to YAML)."""
        self._priorities[skill_name] = self._priorities.get(skill_name, 0.0) + amount

    def find_matching(self, task: str) -> list[dict]:
        """Find skills whose trigger keywords match the task, sorted by priority."""
        self.reload()
        task_lower = task.lower()
        matching = []
        for skill in self._skills.values():
            triggers = skill.get("triggers", [])
            if any(t.lower() in task_lower for t in triggers):
                matching.append(skill)
        matching.sort(
            key=lambda s: self._priorities.get(s.get("name", ""), 0.0),
            reverse=True,
        )
        return matching

    def expand_steps(self, steps: list, depth: int = 0, visited: frozenset | None = None) -> list[str]:
        """Recursively expand skill-reference steps into flat string lists.

        A step can be:
        - ``"plain instruction string"``
        - ``{skill: other_skill_name, input: "optional context"}``

        References are expanded inline up to MAX_SKILL_DEPTH=3.
        Cycles are detected via *visited* and replaced with a placeholder.
        """
        if visited is None:
            visited = frozenset()
        result: list[str] = []
        for step in steps:
            if isinstance(step, str):
                result.append(step)
            elif isinstance(step, dict) and "skill" in step:
                ref_name = str(step["skill"])
                context = step.get("input", "")
                if depth >= _MAX_SKILL_DEPTH or ref_name in visited:
                    result.append(f"[use skill: {ref_name}]")
                    continue
                ref_skill = self._skills.get(ref_name)
                if ref_skill is None:
                    result.append(f"[skill not found: {ref_name}]")
                    continue
                header = f"[{ref_name}: {context}]" if context else f"[{ref_name}]"
                result.append(header)
                sub_steps = self.expand_steps(
                    ref_skill.get("steps", []),
                    depth=depth + 1,
                    visited=visited | {ref_name},
                )
                result.extend(f"  {s}" for s in sub_steps)
            else:
                result.append(str(step))
        return result

    def format_for_prompt(self, skills: list[dict]) -> str:
        """Format skills as instructions for the system prompt, expanding skill references."""
        if not skills:
            return ""
        lines = ["Relevant skills:"]
        for s in skills:
            lines.append(f"- {s.get('name', '?')}: {s.get('description', '')}")
            expanded = self.expand_steps(s.get("steps", []))
            for step in expanded:
                lines.append(f"  * {step}")
        return "\n".join(lines)
