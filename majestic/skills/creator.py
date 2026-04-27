"""
Background skill management — creation and improvement via LLM.

suggest_skill()             — after a complex multi-tool task, decide if worth saving
maybe_improve()             — after every 3rd use, silently improve skill in background
queue_improvement_check()   — after skill invocation, run improvement in BG; user confirms
pop_pending_improvement()   — REPL polls this before each prompt; returns (name, body) or None
"""
import threading

_pending: dict[str, str] = {}   # name → improved body waiting for user confirmation
_pending_lock = threading.Lock()

_SAVE_PROMPT = """\
You are a skill manager for an AI agent called Majestic.

Review this interaction and decide if it should be saved as a reusable skill.
A skill is worth saving when it is: repeatable, multi-step, non-trivial, and generically useful.

User request: {user_input}
Tools used: {tools}
Result summary: {result_summary}

If worth saving, respond with JSON:
{{
  "save": true,
  "name": "short-kebab-case-name",
  "description": "one sentence describing what this skill does",
  "body": "# Skill Name\\n\\n## Goal\\n...\\n\\n## Steps\\n1. ...\\n2. ...\\n\\n## Examples\\n- ...\\n- ..."
}}

If not worth saving (too simple, one-off, or overly specific):
{{"save": false}}

Respond ONLY with JSON, no explanation.\
"""

_IMPROVE_PROMPT = """\
You are a skill manager for an AI agent called Majestic.

This skill has been used {usage_count} times. Improve it based on the recent usage example below.
Keep the Markdown structure. Clarify steps, add useful examples, remove anything outdated.

Current skill body:
{skill_body}

Recent usage:
User: {user_input}
Result: {result_summary}

Return ONLY the improved Markdown body (no frontmatter, no JSON).\
"""


def suggest_skill(
    user_input: str,
    result_summary: str,
    tools_used: list[str],
    lang: str = "EN",
) -> None:
    """Trigger background skill-creation check after a complex interaction."""
    if len(set(tools_used)) < 2:
        return
    threading.Thread(
        target=_run_suggest,
        args=(user_input, result_summary, tools_used, lang),
        daemon=True,
        name="skill-suggest",
    ).start()


def maybe_improve(name: str, user_input: str, result_summary: str) -> None:
    """Trigger background skill improvement after every 3rd use (silent)."""
    from majestic.skills.loader import load_skill
    skill = load_skill(name)
    if not skill:
        return
    if skill["meta"].get("usage_count", 0) % 3 != 0:
        return
    threading.Thread(
        target=_run_improve,
        args=(name, skill, user_input, result_summary),
        daemon=True,
        name="skill-improve",
    ).start()


def queue_improvement_check(name: str, user_input: str, result_summary: str) -> None:
    """
    After skill invocation: check if LLM suggests a better body every 3rd use.
    Result queued in _pending — REPL picks it up before the next prompt.
    """
    from majestic.skills.loader import load_skill
    skill = load_skill(name)
    if not skill:
        return
    if skill["meta"].get("usage_count", 0) % 3 != 0:
        return

    def _run() -> None:
        try:
            improved = _get_improved_body(name, skill, user_input, result_summary)
            if improved and improved.strip() != skill["body"].strip():
                with _pending_lock:
                    _pending[name] = improved
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True, name="skill-improve-check").start()


def pop_pending_improvement() -> tuple[str, str] | None:
    """Return one pending (name, improved_body) and remove it, or None."""
    with _pending_lock:
        if not _pending:
            return None
        name = next(iter(_pending))
        return name, _pending.pop(name)


def _get_improved_body(name: str, skill: dict, user_input: str, result_summary: str) -> str:
    """Run LLM to get an improved skill body. Returns empty string on failure."""
    from majestic.llm import get_provider
    prompt = _IMPROVE_PROMPT.format(
        usage_count=skill["meta"].get("usage_count", 0),
        skill_body=skill["body"][:1200],
        user_input=user_input[:300],
        result_summary=result_summary[:500],
    )
    resp = get_provider().complete([{"role": "user", "content": prompt}])
    return (resp.content or "").strip()


# ── Background workers ────────────────────────────────────────────────────────

def _run_suggest(
    user_input: str,
    result_summary: str,
    tools: list[str],
    lang: str,
) -> None:
    try:
        import json
        from majestic.llm import get_provider
        from majestic.skills.loader import save_skill

        prompt = _SAVE_PROMPT.format(
            user_input=user_input[:300],
            tools=", ".join(sorted(set(tools))),
            result_summary=result_summary[:500],
        )
        resp = get_provider().complete([{"role": "user", "content": prompt}])
        text = resp.content.strip()
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()

        data = json.loads(text)
        if data.get("save") and data.get("name"):
            path = save_skill(
                name=data["name"],
                description=data.get("description", ""),
                body=data.get("body", ""),
            )
            print(f"\n  💡 Skill saved: /{data['name']}  ({path.name})\n", flush=True)
    except Exception:
        pass


def _run_improve(name: str, skill: dict, user_input: str, result_summary: str) -> None:
    try:
        from majestic.skills.loader import update_body
        improved = _get_improved_body(name, skill, user_input, result_summary)
        if improved:
            update_body(name, improved)
    except Exception:
        pass
