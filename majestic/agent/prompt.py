"""System prompt builder for the agentic loop."""

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
    user_tables = _user_tables_schema()
    if user_tables:
        system += f"\n\n## [User tables]\n{user_tables}"
    return system


def _user_tables_schema() -> str:
    """Return a compact schema listing for all user_ tables in state.db."""
    try:
        import sqlite3
        from majestic.constants import DB_PATH
        con = sqlite3.connect(DB_PATH)
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


def build_sub_system(lang: str = "EN") -> str:
    """Minimal system prompt for sub-agents — no memory, no capabilities list."""
    return _SUB_AGENT + f"\n\nRespond in {lang}."
