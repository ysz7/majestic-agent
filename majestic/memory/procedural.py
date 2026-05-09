import yaml
from pathlib import Path


class ProceduralMemory:
    """Loads YAML skill files from profile's skills/ directory. Hot-reloads on change."""

    def __init__(self, skills_dir: str):
        self.skills_dir = Path(skills_dir)
        self._skills: dict[str, dict] = {}
        self._last_modified: dict[str, float] = {}
        self.reload()

    def reload(self):
        """Scan skills_dir and load/reload any changed YAML files."""
        if not self.skills_dir.exists():
            return
        for path in self.skills_dir.glob("*.yaml"):
            mtime = path.stat().st_mtime
            if str(path) not in self._last_modified or self._last_modified[str(path)] < mtime:
                try:
                    with open(path) as f:
                        skill = yaml.safe_load(f)
                    name = skill.get("name") or path.stem
                    self._skills[name] = skill
                    self._last_modified[str(path)] = mtime
                except Exception:
                    pass

    def get_all(self) -> list[dict]:
        self.reload()
        return list(self._skills.values())

    def find_matching(self, task: str) -> list[dict]:
        """Find skills whose trigger keywords match the task."""
        self.reload()
        task_lower = task.lower()
        matching = []
        for skill in self._skills.values():
            triggers = skill.get("triggers", [])
            if any(t.lower() in task_lower for t in triggers):
                matching.append(skill)
        return matching

    def format_for_prompt(self, skills: list[dict]) -> str:
        """Format skills as instructions for the system prompt."""
        if not skills:
            return ""
        lines = ["Relevant skills:"]
        for s in skills:
            lines.append(f"- {s.get('name', '?')}: {s.get('description', '')}")
            if "steps" in s:
                for step in s["steps"]:
                    lines.append(f"  * {step}")
        return "\n".join(lines)
