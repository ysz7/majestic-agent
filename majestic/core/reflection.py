class ReflectionEngine:
    def __init__(self, llm_router, lessons_store, episodic_memory):
        self.llm = llm_router
        self.lessons = lessons_store
        self.episodic = episodic_memory

    async def reflect(
        self,
        task: str,
        result: str,
        steps: list[dict],
        tokens_used: int,
        cost: float,
        duration_s: float,
    ) -> str:
        """
        1. Call LLM (simple model) with task + result + steps
        2. Ask: what went well, what failed, what principle to remember
        3. Extract lesson if one is found
        4. Save to episodic memory
        5. Save lesson to lessons DB
        Returns: reflection text
        """
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

        # Save to episodic
        self.episodic.save_task(
            task=task,
            result=result[:500],
            reflection=reflection_text,
            tokens_used=tokens_used,
            cost=cost,
            duration_s=duration_s,
        )

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
