"""System prompt builder for the agentic loop."""
import time as _time

_prompt_cache: dict = {}  # {"key": (ts, prompt)}
_CACHE_TTL = 30  # seconds — safe since settings/memory rarely change within a session


def _cache_key(lang: str, memory: str) -> str:
    return f"{lang}:{hash(memory)}"

_BASE = """\
You are Majestic, a universal AI agent. You have access to tools to help answer questions and complete tasks.

Guidelines:
- Answer directly from your knowledge when you already know the answer.
- Use tools when you need specific information: documents, web data, market prices.
- For multi-step tasks, use multiple tools in sequence or parallel.
- Be concise and structured in your final answer.
- If a tool returns no useful data, say so and answer from what you know.
- When the user says "save this", "save it", "put this in a report/file" — use write_file with the content of your last response. Do not ask for clarification, just save it immediately.
- Do NOT use delegate_parallel or delegate_task for simple single-step operations (DB lookups, checking data, answering questions). Only use delegation for genuinely parallel multi-source research tasks.
- Confidence: end every final answer with a [confidence: high|medium|low] tag. high = answer came from tools or live data; medium = recent memory or partially verified; low = training knowledge only.
- Planning: for tasks with 3 or more distinct steps, call plan_task first, then update_step as each step completes. Skip for simple single-step tasks.
- Script library: before writing code, check [Script library] — if a matching script exists, use run_script instead. When a task is clearly parametric or recurring (API calls, data fetches, system checks, scheduled work), go script-first: write the script via save_script, then immediately run it with run_script — do NOT use run_python as an intermediate step. After any successful execution, use judgment: save_script only if the logic is genuinely reusable — not for one-off analysis of a specific file or single-use calculations. Never ask the user whether to save — decide yourself.

Built-in capabilities (always available, no tools needed):
- /schedule add <text> — schedule recurring tasks in plain language (cron runs in background)
- /schedule list / remove <id> — manage schedules
- /remind <text> — natural language reminders
- /research — collect fresh intel from HN, Reddit, GitHub, arXiv and more
- /briefing — daily market and tech briefing
- /memory, /forget — persistent memory across sessions
- When the user asks to schedule something recurring, tell them to use /schedule add.\
"""

_SUB_AGENT = """\
You are a sub-agent. Complete the assigned task efficiently using available tools.
Be concise. Return only the final result, no preamble.\
"""


def build_system(lang: str = "EN", memory: str = "") -> str:
    key = _cache_key(lang, memory)
    cached = _prompt_cache.get(key)
    if cached and _time.time() - cached[0] < _CACHE_TTL:
        return cached[1]
    system = _BASE + f"\n\nRespond in {lang}."
    try:
        from majestic import config as _cfg
        role = _cfg.get("agent.role", "")
        if role:
            system += f"\n\n## Role\n{role}"
    except Exception:
        pass
    if memory:
        system += f"\n\n## Persistent memory\n{memory}"
    try:
        from majestic.profile.updater import get_profile_block
        profile = get_profile_block()
        if profile:
            system += f"\n\n## [User profile]\n{profile}"
    except Exception:
        pass
    user_tables = _user_tables_schema()
    if user_tables:
        system += f"\n\n## [User tables]\n{user_tables}"
    scripts = _scripts_list()
    if scripts:
        system += f"\n\n## [Script library]\nUse run_script to execute these saved scripts:\n{scripts}"
    learnings = _recent_learnings()
    if learnings:
        system += f"\n\n## [Recent learnings]\n{learnings}"
    budget = _session_budget()
    if budget:
        system += f"\n\n{budget}"
    _prompt_cache[key] = (_time.time(), system)
    return system


def _scripts_list() -> str:
    """Return compact list of saved scripts for system prompt with usage stats."""
    try:
        from majestic.constants import WORKSPACE_DIR
        from majestic.tools.scripts.metrics import get_all_stats
        d = WORKSPACE_DIR / "scripts"
        if not d.exists():
            return ""
        stats = get_all_stats()
        lines = []
        for p in sorted(d.glob("*.py")):
            try:
                desc = ""
                with p.open(encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("# description: "):
                            desc = line[len("# description: "):].strip()
                            break
                        if not line.startswith("# "):
                            break
                s        = stats.get(p.stem, {})
                runs     = s.get("runs", 0)
                failures = s.get("failures", 0)
                sr       = s.get("success_rate", 0.0)
                parts = [f"- {p.stem}: {desc}"]
                if runs:
                    warn  = f" ⚠{failures} failures" if failures else " ✓"
                    parts.append(f"used {runs}x{warn}")
                if runs > 5 and sr >= 0.8:
                    parts.append("★ ready for promotion")
                lines.append(" · ".join(parts))
            except Exception:
                lines.append(f"- {p.stem}")
        return "\n".join(lines[:20])
    except Exception:
        return ""


def _user_tables_schema() -> str:
    """Return a compact schema listing for all user_ tables in state.db."""
    try:
        import sqlite3
        import majestic.constants as _mc
        con = sqlite3.connect(str(_mc.DB_PATH))
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'user_%'"
        ).fetchall()
        lines = []
        for (name,) in rows:
            info = con.execute(f'PRAGMA table_info("{name}")').fetchall()  # noqa: S608
            cols = [r[1] for r in info if r[1] != "id"]
            lines.append(f"- {name}({', '.join(cols)})")
        con.close()
        return "\n".join(lines)
    except Exception:
        return ""


def _session_budget() -> str:
    try:
        from majestic.token_tracker import get_stats
        d = get_stats()
        tin  = (d.get("tokens_in", 0) or 0) + (d.get("cache_read", 0) or 0)
        cost = d.get("cost_usd", 0.0) or 0.0
        reqs = d.get("requests", 0) or 0
        return f"[Session budget] Tokens: {tin:,} · Cost: ${cost:.4f} · Requests: {reqs}"
    except Exception:
        return ""


def _recent_learnings() -> str:
    try:
        from majestic.agent.reflection import get_recent_learnings
        return get_recent_learnings()
    except Exception:
        return ""


def build_sub_system(lang: str = "EN") -> str:
    """Minimal system prompt for sub-agents — no memory, no capabilities list."""
    return _SUB_AGENT + f"\n\nRespond in {lang}."
