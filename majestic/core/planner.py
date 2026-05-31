class Planner:
    def __init__(self, settings, llm_router, lessons_store=None):
        self.settings = settings
        self.llm = llm_router
        self.lessons = lessons_store

    def classify_task(self, task: str) -> str:
        """Classify task to determine default model type."""
        task_lower = task.lower()
        if any(w in task_lower for w in ["code", "implement", "write code", "fix", "debug", "script"]):
            return "code"
        if any(w in task_lower for w in ["search", "find", "research", "web", "look up"]):
            return "simple"
        if any(w in task_lower for w in ["analyze", "plan", "design", "think", "reason", "compare"]):
            return "reason"
        return "reason"

    def get_lessons_context(self, task: str) -> str:
        """Load top-3 relevant lessons and format as context string."""
        if not self.lessons:
            return ""
        lessons = self.lessons.search(task, limit=3)
        if not lessons:
            return ""
        lines = ["Previous lessons learned:"]
        for l in lessons:
            lines.append(f"- {l['lesson']}")
        return "\n".join(lines)

    def get_available_agents(self) -> list[dict]:
        """Return all agent profiles with role info and running status.

        Includes both running and stopped agents so the LLM can decide
        whether to auto-start one via delegate_to_agent.
        """
        import yaml
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent.parent
        profiles_dir = root / "profiles"

        # Single source of truth — SQLite registry (registry.json is legacy).
        try:
            from majestic.cli.registry_db import load_registry
            registry = load_registry()
        except Exception:
            registry = {}

        result = []
        if not profiles_dir.exists():
            return result

        for entry in sorted(profiles_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue

            persona: dict = {}
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
                "name": entry.name,
                "agent_name": persona.get("name", entry.name),
                "role": persona.get("role", "General assistant"),
                "running": bool(running_info),
                "port": running_info.get("port") or persona.get("port"),
            })

        return result

    async def decompose(self, task: str) -> list[str]:
        """Break a complex task into subtasks using LLM."""
        prompt = f"""Break this task into 3-5 concrete subtasks. Return ONLY a numbered list.

Task: {task}"""
        response = await self.llm.chat(
            [{"role": "user", "content": prompt}],
            step_type="reason"
        )
        lines = response["content"].strip().split("\n")
        subtasks = []
        for line in lines:
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith("-")):
                subtask = line.lstrip("0123456789.-) ").strip()
                if subtask:
                    subtasks.append(subtask)
        return subtasks or [task]

    def needs_hitl(self, task: str) -> bool:
        """Return True if task requires human approval before execution."""
        sensitive = ["delete", "rm -rf", "drop table", "format", "wipe", "overwrite all"]
        return any(s in task.lower() for s in sensitive)
