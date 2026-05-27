import logging

logger = logging.getLogger(__name__)


class MemoryConsolidator:
    """Distills episodic task history into semantic knowledge patterns.

    Every CONSOLIDATE_EVERY new tasks, groups recent episodes by type,
    extracts 2-3 behavioral patterns via LLM, and indexes them into semantic.db
    so future RAG queries can surface them as context.
    """

    CONSOLIDATE_EVERY = 50
    BATCH_SIZE = 20

    def __init__(self, episodic, semantic, user_profile, llm_router):
        self.episodic = episodic
        self.semantic = semantic
        self.user_profile = user_profile
        self.llm = llm_router

    async def maybe_consolidate(self) -> int:
        """Run consolidation if CONSOLIDATE_EVERY new tasks have accumulated.

        Returns the number of pattern groups saved to semantic.db.
        """
        total = self.episodic.count()
        try:
            last = int(self.user_profile.get("consolidation_last_task_count", "0"))
        except (ValueError, TypeError):
            last = 0
        if total - last < self.CONSOLIDATE_EVERY:
            return 0
        count = await self.consolidate()
        self.user_profile.set("consolidation_last_task_count", str(total))
        return count

    async def consolidate(self) -> int:
        """Distill recent episodes into semantic patterns.

        Returns the number of pattern groups indexed into semantic.db.
        """
        episodes = self.episodic.get_recent(self.BATCH_SIZE)
        if not episodes:
            return 0

        groups: dict[str, list] = {}
        for ep in episodes:
            t = self._classify(ep["task"])
            groups.setdefault(t, []).append(ep)

        saved = 0
        for task_type, group in groups.items():
            if len(group) < 2:
                continue
            pattern = await self._extract_patterns(task_type, group)
            if pattern:
                self.semantic.index(
                    source=f"memory_consolidation/{task_type}",
                    content=pattern,
                    chunk_size=500,
                )
                saved += 1

        return saved

    async def _extract_patterns(self, task_type: str, episodes: list) -> str | None:
        examples = "\n\n".join(
            f"Task: {ep['task'][:120]}\nResult: {ep['result'][:200]}"
            for ep in episodes[:5]
        )
        prompt = (
            f"Analyze these {task_type} tasks and extract 2-3 key behavioral patterns.\n"
            f"Focus on what worked well and what to remember for future similar tasks.\n\n"
            f"{examples}\n\n"
            f"Return ONLY 2-3 concise bullet points (principles/patterns learned):"
        )
        try:
            resp = await self.llm.chat(
                [{"role": "user", "content": prompt}],
                step_type="simple",
            )
            text = resp["content"].strip()
            return text if len(text) > 10 else None
        except Exception as exc:
            logger.warning("MemoryConsolidator LLM call failed: %s", exc)
            return None

    @staticmethod
    def _classify(task: str) -> str:
        t = task.lower()
        if any(w in t for w in ["code", "write", "implement", "fix", "debug", "script"]):
            return "coding"
        if any(w in t for w in ["search", "find", "research", "look up", "browse"]):
            return "research"
        if any(w in t for w in ["analyze", "summarize", "explain", "review"]):
            return "analysis"
        return "general"
