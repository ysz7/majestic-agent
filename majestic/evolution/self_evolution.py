import asyncio
import shutil
from pathlib import Path
from datetime import datetime, timezone

from majestic import display


class SelfEvolution:
    """
    Self-evolution engine: three triggers for auto-generating reusable artifacts.

    Trigger 1 — Skill auto-generation
        After every task reflection: if the task was multi-step and repeatable,
        generate a YAML skill and save to profiles/[name]/skills/.

    Trigger 2 — Script promotion (temp → tools)
        If a script executed successfully and produced useful output,
        move it from workspace/temp/ to workspace/tools/ automatically.

    Trigger 3 — Script parameterization (3+ runs with variations)
        Detect scripts that ran 3+ times. Generate a parameterized version
        and save it to workspace/tools/ as a reusable utility.

    Artifact improvement:
        - Skill gave poor result → update its YAML via LLM
        - Script crashed → fix it, save fixed version, add lesson to lessons.db
    """

    def __init__(
        self,
        llm_router,
        skill_writer,
        script_tracker,
        lessons_store,
        workspace_dir: str,
        procedural_memory=None,
    ):
        self.llm = llm_router
        self.skill_writer = skill_writer
        self.tracker = script_tracker
        self.lessons = lessons_store
        self.procedural = procedural_memory
        self.workspace = Path(workspace_dir)
        self.tools_dir = self.workspace / "tools"
        self.temp_dir = self.workspace / "temp"
        self.tools_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Main entry point — called by ReflectionEngine after every task      #
    # ------------------------------------------------------------------ #

    async def run(
        self,
        task: str,
        steps: list[dict],
        reflection: str,
        skill_quality_ok: bool = True,
        used_skill: str | None = None,
        result: str = "",
    ):
        """
        Run all three triggers after task completion.
        Call this from ReflectionEngine.reflect().
        """
        results = await asyncio.gather(
            self._trigger1_skill_generation(task, steps, reflection),
            self._trigger3_parameterize_repeats(),
            return_exceptions=True,
        )

        skill_name = results[0] if not isinstance(results[0], Exception) else None
        if skill_name:
            display.tree_step("skill", skill_name)

        # Trigger 2 runs synchronously (file ops only)
        self._trigger2_promote_scripts(steps)

        # Artifact improvement from explicit quality flag
        if not skill_quality_ok and used_skill:
            await self._improve_skill(used_skill, task, reflection)

        await self._fix_failed_scripts(steps)

        # Judge pattern: score skill result, improve or boost based on history
        if used_skill and result:
            await self._run_judge(task, result, used_skill)

        return {
            "skill_generated": skill_name,
            "scripts_parameterized": results[1] if not isinstance(results[1], Exception) else 0,
        }

    # ------------------------------------------------------------------ #
    # Trigger 1 — Skill auto-generation                                   #
    # ------------------------------------------------------------------ #

    async def _trigger1_skill_generation(
        self,
        task: str,
        steps: list[dict],
        reflection: str,
    ) -> str | None:
        """Generate a YAML skill if the task was multi-step and repeatable."""
        name = await self.skill_writer.maybe_generate(task, steps, reflection)
        if name:
            self.lessons.save(
                task_type="meta",
                lesson=f"Created skill '{name}' from task: {task[:80]}",
            )
        return name

    # ------------------------------------------------------------------ #
    # Trigger 2 — Script promotion (temp → tools)                         #
    # ------------------------------------------------------------------ #

    def _trigger2_promote_scripts(self, steps: list[dict]):
        """
        For each successful python_exec / node_exec step, save the script to
        workspace/tools/ if it produced useful output and isn't already there.
        """
        for step in steps:
            if step.get("tool") not in ("python_exec", "node_exec"):
                continue

            result_text = str(step.get("result", ""))
            is_success = result_text and not any(
                sig in result_text.lower()
                for sig in ("error", "traceback", "exception", "timed out")
            )
            if not is_success:
                continue

            # code may be nested in args (runtime format) or at top level (test/legacy)
            args = step.get("args", {})
            code = args.get("code") or step.get("code", "")
            if not code or len(code) < 30:
                continue

            lang = "python" if step.get("tool") == "python_exec" else "node"
            ext = ".py" if lang == "python" else ".js"
            name = self._derive_script_name(code, ext)
            dest = self.tools_dir / name

            if dest.exists():
                continue  # already promoted

            dest.write_text(code, encoding="utf-8")
            display.tree_step("promoted", dest.name)
            self.lessons.save(
                task_type="meta",
                lesson=f"Promoted reusable script → {dest.name}",
            )

            # Mark as promoted in the tracker so should_promote() returns False
            run_id = step.get("script_run_id")
            if run_id is not None:
                try:
                    self.tracker.mark_promoted(
                        run_id,
                        str(dest),
                        description=f"Auto-promoted from task execution",
                    )
                except Exception:
                    pass

    # ------------------------------------------------------------------ #
    # Trigger 3 — Script parameterization                                 #
    # ------------------------------------------------------------------ #

    async def _trigger3_parameterize_repeats(self) -> int:
        """
        Find script groups with 3+ runs and generate parameterized versions.
        Returns count of parameterized scripts created.
        """
        groups = self.tracker.detect_repeats()
        created = 0

        for group in groups:
            variations = self.tracker.get_variations(group["code_hash"])
            if len(variations) < self.tracker.REPEAT_THRESHOLD:
                continue

            parameterized = await self._generate_parameterized(
                group["lang"],
                group["sample_code"],
                variations,
            )
            if not parameterized:
                continue

            ext = ".py" if group["lang"] == "python" else ".js"
            name = self._derive_script_name(parameterized, ext)
            dest = self.tools_dir / f"param_{name}"

            if not dest.exists():
                dest.write_text(parameterized, encoding="utf-8")
                display.tree_step("parameterized", f"{dest.name}  ·  {len(variations)} runs merged")

                # Mark all runs in this group as promoted
                for var in variations:
                    self.tracker.mark_promoted(
                        var["id"],
                        str(dest),
                        description=f"Parameterized from {len(variations)} similar runs",
                    )

                self.lessons.save(
                    task_type="meta",
                    lesson=f"Parameterized repeated script → {dest.name} ({len(variations)} runs merged)",
                )
                created += 1

        return created

    async def _generate_parameterized(
        self,
        lang: str,
        sample_code: str,
        variations: list[dict],
    ) -> str | None:
        """Use LLM to create a parameterized version from multiple similar scripts."""
        variations_text = "\n\n---\n".join(
            f"Run {i+1}:\n{v['code'][:400]}" for i, v in enumerate(variations[:5])
        )

        lang_name = "Python" if lang == "python" else "Node.js"
        prompt = f"""These {lang_name} scripts do the same thing with slight variations.
Create ONE parameterized version that accepts arguments to cover all cases.

Sample runs:
{variations_text}

Return ONLY the {lang_name} code with:
- A main function / entry point that accepts parameters
- Clear parameter names
- A brief docstring/comment explaining usage
- No hardcoded values that vary between runs
- At the bottom: example of how to call it

Return ONLY the code, no markdown fences."""

        response = await self.llm.chat(
            [{"role": "user", "content": prompt}],
            step_type="code",
        )
        code = response["content"].strip()

        # Strip markdown fences if present
        import re
        code = re.sub(r"^```\w*\s*", "", code, flags=re.IGNORECASE)
        code = re.sub(r"```\s*$", "", code).strip()

        return code if len(code) > 20 else None

    # ------------------------------------------------------------------ #
    # Artifact improvement — skill quality                                 #
    # ------------------------------------------------------------------ #

    async def _improve_skill(self, skill_name: str, task: str, bad_result: str):
        """Update a skill YAML when it produced a poor result."""
        updated = await self.skill_writer.update_skill(skill_name, bad_result, task)
        if updated:
            self.lessons.save(
                task_type="meta",
                lesson=f"Improved skill '{skill_name}' after poor result on: {task[:80]}",
            )

    # ------------------------------------------------------------------ #
    # Artifact improvement — fix failed scripts                           #
    # ------------------------------------------------------------------ #

    async def _fix_failed_scripts(self, steps: list[dict]):
        """For each failed script step, ask LLM to fix it and save fixed version."""
        for step in steps:
            if step.get("tool") not in ("python_exec", "node_exec"):
                continue

            result_text = str(step.get("result", ""))
            # Detect failure from result text (runtime doesn't set a success flag)
            is_failure = any(
                sig in result_text.lower()
                for sig in ("error", "traceback", "exception", "stderr")
            )
            if not is_failure:
                continue

            # Code is stored in step["args"]["code"], not step["code"]
            args = step.get("args", {})
            code = args.get("code", "")
            error = result_text[:500]
            lang = "Python" if step.get("tool") == "python_exec" else "Node.js"

            if not code or not error:
                continue

            fixed = await self._ask_fix(lang, code, error)
            if not fixed:
                continue

            ext = ".py" if lang == "Python" else ".js"
            name = self._derive_script_name(fixed, ext)
            dest = self.tools_dir / f"fixed_{name}"

            if not dest.exists():
                dest.write_text(fixed, encoding="utf-8")
                display.tree_step("fixed", dest.name)
                self.lessons.save(
                    task_type="coding",
                    lesson=f"Fixed {lang} script error: {error[:120]}. Fixed version saved as {dest.name}",
                )

    async def _ask_fix(self, lang: str, code: str, error: str) -> str | None:
        prompt = f"""Fix this {lang} script. Return ONLY the corrected code.

Script:
{code}

Error:
{error}

Return ONLY the fixed code, no explanation, no markdown fences."""

        try:
            response = await self.llm.chat(
                [{"role": "user", "content": prompt}],
                step_type="code",
            )
            import re
            fixed = re.sub(r"^```\w*\s*", "", response["content"].strip(), flags=re.IGNORECASE)
            fixed = re.sub(r"```\s*$", "", fixed).strip()
            return fixed if len(fixed) > 10 else None
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    # Judge pattern — skill quality evaluation                            #
    # ------------------------------------------------------------------ #

    async def _run_judge(self, task: str, result: str, skill_name: str) -> None:
        """Score a skill's output and trigger improvement or priority boost."""
        score = await self._judge_skill_result(task, result, skill_name)
        self.lessons.save_skill_score(skill_name, score)
        recent = self.lessons.get_skill_scores(skill_name, limit=3)
        label = f"{skill_name}  {score:.2f}"
        if len(recent) >= 3:
            avg = sum(recent[:3]) / 3
            if avg < 0.4:
                display.tree_step("skill-judge", f"{label}  → improving")
                await self._improve_skill(skill_name, task, result)
            elif avg > 0.8:
                if self.procedural:
                    self.procedural.boost_priority(skill_name)
                display.tree_step("skill-judge", f"{label}  → top-rated")
                self.lessons.save(
                    task_type="meta",
                    lesson=f"Skill '{skill_name}' consistently delivers excellent results — prefer it",
                )
            else:
                display.tree_step("skill-judge", label)
        else:
            display.tree_step("skill-judge", label)

    async def _judge_skill_result(self, task: str, result: str, skill_name: str) -> float:
        """Ask LLM to score result quality 0.0 (failed) → 1.0 (perfect)."""
        prompt = (
            f"Rate the quality of this task result from 0.0 (failed/useless) to 1.0 (perfect/complete).\n\n"
            f"Skill used: {skill_name}\n"
            f"Task: {task[:200]}\n"
            f"Result: {result[:300]}\n\n"
            f"Return ONLY a single decimal number between 0.0 and 1.0 (e.g. 0.8):"
        )
        try:
            import re
            resp = await self.llm.chat(
                [{"role": "user", "content": prompt}],
                step_type="simple",
            )
            m = re.search(r"[01]?\.\d+|^[01]$", resp["content"].strip())
            score = float(m.group()) if m else 0.5
            return max(0.0, min(1.0, score))
        except Exception:
            return 0.5

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _derive_script_name(code: str, ext: str) -> str:
        """Derive a filename from the first meaningful comment or def/function line."""
        import re
        for line in code.splitlines():
            line = line.strip()
            # Python def / Node function
            m = re.match(r"(?:def|async def|function)\s+(\w+)", line)
            if m:
                return f"{m.group(1)}{ext}"
            # Comment describing the script
            m = re.match(r"#\s*(.+)", line)
            if m:
                name = re.sub(r"[^a-z0-9]+", "_", m.group(1).lower())[:30].strip("_")
                if name:
                    return f"{name}{ext}"

        ts = datetime.now(timezone.utc).strftime("%H%M%S")
        return f"script_{ts}{ext}"
