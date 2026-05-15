import yaml
import re
from pathlib import Path
from datetime import datetime


class SkillWriter:
    """
    Generates YAML skill files from task experience using LLM.
    Validates structure, saves to profile's skills/ directory.
    Hot-reload picks them up immediately (no restart needed).
    """

    REQUIRED_KEYS = {"name", "description", "triggers", "steps"}

    def __init__(self, llm_router, skills_dir: str):
        self.llm = llm_router
        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    async def maybe_generate(
        self,
        task: str,
        steps: list[dict],
        reflection: str,
    ) -> str | None:
        """
        Decide whether to generate a skill. If yes, generate + save.
        Returns the skill name if saved, None otherwise.
        """
        if not self._is_worth_skilling(steps, reflection):
            return None

        skill_yaml = await self._generate(task, steps)
        if not skill_yaml:
            return None

        return self._save(skill_yaml)

    async def update_skill(
        self,
        skill_name: str,
        bad_result: str,
        task: str,
    ) -> bool:
        """
        Update an existing skill YAML when it gave a poor result.
        Returns True if updated successfully.
        """
        skill_path = self.skills_dir / f"{skill_name}.yaml"
        if not skill_path.exists():
            return False

        with open(skill_path) as f:
            existing = yaml.safe_load(f)

        prompt = f"""A skill gave a poor result. Improve it.

Skill name: {skill_name}
Current skill YAML:
{yaml.dump(existing, allow_unicode=True)}

Task that used this skill: {task}
What went wrong: {bad_result[:500]}

Return ONLY the improved YAML (same structure, same keys).
Add or fix steps to handle the failure. Add trigger phrases if needed.
Do not add commentary, only YAML."""

        response = await self.llm.chat(
            [{"role": "user", "content": prompt}],
            step_type="simple",
        )

        updated = self._parse_yaml(response["content"])
        if not updated:
            return False

        updated["name"] = existing.get("name", skill_name)
        updated["updated_at"] = datetime.utcnow().isoformat()

        tmp = skill_path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            yaml.dump(updated, f, default_flow_style=False, allow_unicode=True)
        tmp.replace(skill_path)

        return True

    def _is_worth_skilling(self, steps: list[dict], reflection: str) -> bool:
        """
        Heuristic: worth generating a skill if:
        - 3+ distinct tool steps were taken
        - reflection doesn't indicate total failure
        """
        if len(steps) < 3:
            return False
        failure_signals = ["failed", "error", "couldn't", "unable to", "gave up"]
        if any(s in reflection.lower() for s in failure_signals):
            return False
        return True

    async def _generate(self, task: str, steps: list[dict]) -> dict | None:
        steps_summary = "\n".join(
            f"- {s.get('tool', 'think')}: {str(s.get('result', ''))[:80]}"
            for s in steps[:15]
        )

        prompt = f"""You are analyzing a completed agent task to extract a reusable skill.

Task: {task}

Steps taken:
{steps_summary}

Generate a YAML skill file that captures the essence of this workflow so the agent can reuse it.

Return ONLY valid YAML with this exact structure:
```yaml
name: "short_snake_case_name"
description: "One sentence: what this skill does"
triggers:
  - "trigger phrase 1"
  - "trigger phrase 2"
  - "trigger phrase 3"
steps:
  - "Step 1: ..."
  - "Step 2: ..."
  - "Step 3: ..."
```

Rules:
- name: snake_case, max 30 chars, no spaces
- triggers: 3-5 short phrases a user might say to invoke this skill
- steps: 3-7 concrete action steps (not vague)
- Return ONLY the YAML block, no explanation"""

        response = await self.llm.chat(
            [{"role": "user", "content": prompt}],
            step_type="simple",
        )

        return self._parse_yaml(response["content"])

    def _parse_yaml(self, text: str) -> dict | None:
        # Strip markdown code fences if present
        text = re.sub(r"^```ya?ml\s*", "", text.strip(), flags=re.IGNORECASE)
        text = re.sub(r"```\s*$", "", text.strip())

        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError:
            return None

        if not isinstance(data, dict):
            return None

        missing = self.REQUIRED_KEYS - set(data.keys())
        if missing:
            return None

        if not isinstance(data.get("triggers"), list) or not data["triggers"]:
            return None
        if not isinstance(data.get("steps"), list) or not data["steps"]:
            return None

        return data

    def _save(self, skill: dict) -> str | None:
        name = re.sub(r"[^a-z0-9_]", "_", str(skill.get("name", "skill")).lower())
        name = name[:30].strip("_")
        if not name:
            return None

        skill["name"] = name
        skill["auto_generated"] = True
        skill["created_at"] = datetime.utcnow().isoformat()

        dest = self.skills_dir / f"{name}.yaml"

        # Guard against path traversal (name is already [a-z0-9_] but be explicit)
        if not str(dest.resolve()).startswith(str(self.skills_dir.resolve())):
            return None

        # Don't overwrite manually-created skills (those without auto_generated flag)
        if dest.exists():
            with open(dest) as f:
                existing = yaml.safe_load(f) or {}
            if not existing.get("auto_generated"):
                name = f"{name}_v2"
                dest = self.skills_dir / f"{name}.yaml"

        tmp = dest.with_suffix(".tmp")
        with open(tmp, "w") as f:
            yaml.dump(skill, f, default_flow_style=False, allow_unicode=True)
        tmp.replace(dest)

        return name
