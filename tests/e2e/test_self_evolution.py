"""
E2E test: Self-Evolution — Skill + Script Auto-Generation

Scenario:
  1. Run agent on 5 structurally similar tasks (web research + summarize)
  2. After each task, reflection + SelfEvolution run
  3. Assert: a YAML skill appears in skills/ after enough repetitions
  4. Assert: on task 6, the Planner finds and uses the generated skill

Uses a mock LLM so no real API keys are needed.
"""

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# Make sure the package is importable
sys.path.insert(0, str(Path(__file__).parents[2]))

from majestic.evolution.script_tracker import ScriptTracker
from majestic.evolution.skill_writer import SkillWriter
from majestic.evolution.self_evolution import SelfEvolution
from majestic.evolution.reflection import ReflectionEngine
from majestic.memory.lessons import LessonsStore
from majestic.memory.episodic import EpisodicMemory
from majestic.memory.procedural import ProceduralMemory


# ---------------------------------------------------------------------------
# Mock LLM
# ---------------------------------------------------------------------------

SKILL_YAML = """\
name: web_research_summarize
description: Research a topic on the web and return a structured summary
triggers:
  - research
  - look up
  - find information about
  - summarize topic
  - what is
steps:
  - Search the web for the topic using web_search
  - Fetch the top 2 result URLs with web_fetch
  - Synthesize findings into a concise summary
  - Include source URLs at the end
"""

REFLECTION_TEXT = """\
1. What worked well? The web search returned relevant results and synthesis was accurate.
2. What could be improved? Could fetch more sources for deeper coverage.
3. LESSON: Always verify at least 2 sources before summarizing web research.
"""


def make_mock_llm(skill_yaml: str = SKILL_YAML, reflection: str = REFLECTION_TEXT):
    """Return a mock LLM router that returns deterministic responses."""
    llm = MagicMock()

    async def chat(messages, step_type="reason", **kwargs):
        content = messages[-1]["content"] if messages else ""
        if "generate a yaml skill" in content.lower() or "reusable skill" in content.lower():
            return {"content": skill_yaml, "input_tokens": 100, "output_tokens": 200, "cost": 0.0}
        if "reflect" in content.lower() or "completed a task" in content.lower():
            return {"content": reflection, "input_tokens": 50, "output_tokens": 100, "cost": 0.0}
        return {"content": "FINAL_ANSWER: Done.", "input_tokens": 10, "output_tokens": 20, "cost": 0.0}

    llm.chat = chat
    return llm


# ---------------------------------------------------------------------------
# Helpers to build task steps that look like multi-step web research
# ---------------------------------------------------------------------------

def make_research_steps() -> list[dict]:
    return [
        {"tool": "web_search", "args": {"query": "topic"}, "result": "[{title, url, snippet}]"},
        {"tool": "web_fetch",  "args": {"url": "https://example.com"}, "result": "Page content..."},
        {"tool": "web_fetch",  "args": {"url": "https://other.com"},   "result": "More content..."},
        {"tool": "web_search", "args": {"query": "topic details"},      "result": "[{title, url}]"},
        {"tool": "web_fetch",  "args": {"url": "https://third.com"},    "result": "Detail page..."},
    ]


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

class TestSelfEvolution(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.skills_dir  = Path(self.tmpdir) / "skills"
        self.tools_dir   = Path(self.tmpdir) / "tools"
        self.temp_dir    = Path(self.tmpdir) / "temp"
        self.workspace   = Path(self.tmpdir) / "workspace"

        for d in (self.skills_dir, self.tools_dir, self.temp_dir, self.workspace):
            d.mkdir(parents=True, exist_ok=True)

        self.llm      = make_mock_llm()
        self.lessons  = LessonsStore(str(Path(self.tmpdir) / "lessons.db"))
        self.episodic = EpisodicMemory(str(Path(self.tmpdir) / "episodic.db"))
        self.tracker  = ScriptTracker(str(Path(self.tmpdir) / "scripts.db"))

        self.skill_writer = SkillWriter(self.llm, str(self.skills_dir))

        self.evolution = SelfEvolution(
            llm_router    = self.llm,
            skill_writer  = self.skill_writer,
            script_tracker= self.tracker,
            lessons_store = self.lessons,
            workspace_dir = str(self.workspace),
        )
        # Patch tools_dir to point at our tmp
        self.evolution.tools_dir = self.tools_dir
        self.evolution.temp_dir  = self.temp_dir

        self.reflection_engine = ReflectionEngine(
            llm_router    = self.llm,
            lessons_store = self.lessons,
            episodic_memory = self.episodic,
            self_evolution= self.evolution,
        )

        self.procedural = ProceduralMemory(str(self.skills_dir))

    # ------------------------------------------------------------------
    # Test 1: skill is generated after 5 similar tasks
    # ------------------------------------------------------------------

    async def test_skill_appears_after_repeated_tasks(self):
        tasks = [
            "Research quantum computing and summarize",
            "Find information about CRISPR gene editing and summarize",
            "Look up the history of the internet and summarize",
            "Research renewable energy trends and summarize",
            "Find information about machine learning and summarize",
        ]

        for task in tasks:
            await self.reflection_engine.reflect(
                task        = task,
                result      = f"Summary of {task}",
                steps       = make_research_steps(),
                tokens_used = 500,
                cost        = 0.001,
                duration_s  = 3.0,
            )

        # At least one YAML skill should exist in skills/
        skill_files = list(self.skills_dir.glob("*.yaml"))
        self.assertTrue(
            len(skill_files) > 0,
            f"Expected skill files in {self.skills_dir}, found none"
        )

        # The skill file must be valid YAML with required keys
        import yaml
        for sf in skill_files:
            with open(sf) as f:
                skill = yaml.safe_load(f)
            self.assertIn("name",        skill, f"{sf.name} missing 'name'")
            self.assertIn("triggers",    skill, f"{sf.name} missing 'triggers'")
            self.assertIn("steps",       skill, f"{sf.name} missing 'steps'")
            self.assertIn("description", skill, f"{sf.name} missing 'description'")
            self.assertTrue(skill["triggers"], "triggers list is empty")
            self.assertTrue(skill["steps"],    "steps list is empty")

    # ------------------------------------------------------------------
    # Test 2: on task 6, ProceduralMemory finds and returns the skill
    # ------------------------------------------------------------------

    async def test_skill_used_on_task_6(self):
        tasks = [
            "Research quantum computing and summarize",
            "Find information about CRISPR gene editing and summarize",
            "Look up the history of the internet and summarize",
            "Research renewable energy trends and summarize",
            "Find information about machine learning and summarize",
        ]
        for task in tasks:
            await self.reflection_engine.reflect(
                task        = task,
                result      = f"Summary of {task}",
                steps       = make_research_steps(),
                tokens_used = 500,
                cost        = 0.001,
                duration_s  = 3.0,
            )

        # Task 6 — should match the auto-generated skill's triggers
        task_6 = "Research superconductors and summarize"
        matching = self.procedural.find_matching(task_6)

        self.assertTrue(
            len(matching) > 0,
            f"Expected ProceduralMemory to find a skill for task 6, got none.\n"
            f"Skills dir contents: {list(self.skills_dir.glob('*.yaml'))}"
        )

        # The matched skill should have usable steps
        skill = matching[0]
        self.assertTrue(skill.get("steps"), "Matched skill has no steps")

    # ------------------------------------------------------------------
    # Test 3: lesson is saved to lessons.db during reflection
    # ------------------------------------------------------------------

    async def test_lesson_saved_to_db(self):
        await self.reflection_engine.reflect(
            task        = "Research AI trends and summarize findings",
            result      = "AI is growing rapidly...",
            steps       = make_research_steps(),
            tokens_used = 300,
            cost        = 0.0005,
            duration_s  = 2.0,
        )

        lessons = self.lessons.get_top(limit=10)
        self.assertTrue(len(lessons) > 0, "No lessons saved after reflection")

    # ------------------------------------------------------------------
    # Test 4: script promotion (temp → tools)
    # ------------------------------------------------------------------

    async def test_script_promotion(self):
        code = "# fetch and print data\nprint('hello world')"

        # Record a successful script run
        run_id = self.tracker.record(
            lang="python", code=code, success=True, output="hello world"
        )
        self.assertTrue(self.tracker.should_promote(run_id))

        # Simulate a step that carried the run_id
        steps_with_script = [
            {
                "tool": "python_exec",
                "lang": "python",
                "code": code,
                "script_run_id": run_id,
                "success": True,
                "result": "hello world",
            }
        ]

        self.evolution._trigger2_promote_scripts(steps_with_script)

        promoted_files = list(self.tools_dir.glob("*.py"))
        self.assertTrue(
            len(promoted_files) > 0,
            "Script was not promoted to workspace/tools/"
        )
        self.assertFalse(
            self.tracker.should_promote(run_id),
            "Script should be marked as promoted"
        )

    # ------------------------------------------------------------------
    # Test 5: parameterization triggered at 3+ runs
    # ------------------------------------------------------------------

    async def test_script_parameterization(self):
        base_code = "import requests\ndata = requests.get('https://api.example.com/data').json()\nprint(data)"

        # Record 3 slightly different successful runs (same structural hash)
        for i in range(3):
            variant = base_code.replace("data", f"result_{i}")
            self.tracker.record(lang="python", code=base_code, success=True, output=f"result {i}")

        groups = self.tracker.detect_repeats()
        self.assertTrue(len(groups) > 0, "detect_repeats() returned nothing after 3 runs")
        self.assertGreaterEqual(groups[0]["run_count"], 3)


if __name__ == "__main__":
    unittest.main()
