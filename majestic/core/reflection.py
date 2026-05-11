from majestic import display


class ReflectionEngine:
    def __init__(self, llm_router, lessons_store, episodic_memory, self_evolution=None):
        self.llm = llm_router
        self.lessons = lessons_store
        self.episodic = episodic_memory
        self.evolution = self_evolution  # SelfEvolution | None

    async def reflect(
        self,
        task: str,
        result: str,
        steps: list[dict],
        tokens_used: int,
        cost: float,
        duration_s: float,
        used_skill: str | None = None,
        skill_quality_ok: bool = True,
    ) -> str:
        """
        1. Call LLM (simple model) with task + result + steps
        2. Ask: what went well, what failed, what principle to remember
        3. Extract lesson if one is found
        4. Save to episodic memory + lessons DB
        5. Run SelfEvolution: skill generation, script promotion, parameterization
        Returns: reflection text
        """
        display.reflection_start()

        prompt = self._build_reflection_prompt(task, result, steps)
        response = await self.llm.chat(
            [{"role": "user", "content": prompt}],
            step_type="reflection",
        )
        reflection_text = response["content"]

        # Extract lesson if present
        lesson = self._extract_lesson(reflection_text)
        if lesson:
            self.lessons.save(task_type=self._classify_task(task), lesson=lesson)
            display.lesson_saved(lesson)

        # Save to episodic
        self.episodic.save_task(
            task=task,
            result=result[:500],
            reflection=reflection_text,
            tokens_used=tokens_used,
            cost=cost,
            duration_s=duration_s,
        )

        # Self-evolution: generate skills, promote scripts, fix failures
        if self.evolution:
            try:
                await self.evolution.run(
                    task=task,
                    steps=steps,
                    reflection=reflection_text,
                    skill_quality_ok=skill_quality_ok,
                    used_skill=used_skill,
                )
            except Exception:
                pass  # evolution is non-fatal

        return reflection_text

    def _build_reflection_prompt(self, task: str, result: str, steps: list[dict]) -> str:
        steps_summary = "\n".join(
            f"- {s.get('tool', '?')}: {str(s.get('result', ''))[:100]}"
            for s in steps[:10]
        )
        return f"""You completed a task. Reflect briefly.

Task: {task}
Result: {result[:300]}
Steps taken:
{steps_summary}

Reflect in 2-3 sentences:
1. What worked well?
2. What could be improved?
3. LESSON: <one reusable principle to remember, or "none">"""

    def _extract_lesson(self, reflection: str) -> str | None:
        for line in reflection.split("\n"):
            if line.strip().upper().startswith("LESSON:"):
                lesson = line.split(":", 1)[1].strip()
                if lesson.lower() not in ("", "none"):
                    return lesson
        return None

    def _classify_task(self, task: str) -> str:
        task_lower = task.lower()
        if any(w in task_lower for w in ["code", "write", "implement", "fix", "debug"]):
            return "coding"
        if any(w in task_lower for w in ["search", "find", "research", "look up"]):
            return "research"
        if any(w in task_lower for w in ["analyze", "summarize", "explain"]):
            return "analysis"
        return "general"
