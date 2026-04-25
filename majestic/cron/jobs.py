"""
Schedule CRUD and natural-language scheduling.

Schedules live in the `schedules` table in StateDB.
Each schedule has: name, cron_expr, prompt, delivery_target, last_run, next_run, enabled.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional


# ── CRUD ──────────────────────────────────────────────────────────────────────

def add_schedule(
    name: str,
    cron_expr: str,
    prompt: str,
    delivery_target: str = "cli",
) -> dict:
    """Insert a new schedule. Returns the created row as dict."""
    from majestic.db.state import StateDB
    from croniter import croniter

    next_run = croniter(cron_expr, datetime.now()).get_next(datetime).isoformat()
    db = StateDB()
    db._conn.execute(
        """INSERT INTO schedules(name, cron_expr, prompt, delivery_target, next_run, enabled)
           VALUES (?, ?, ?, ?, ?, 1)""",
        (name, cron_expr, prompt, delivery_target, next_run),
    )
    db._conn.commit()
    row = db._conn.execute(
        "SELECT * FROM schedules WHERE name = ? ORDER BY id DESC LIMIT 1", (name,)
    ).fetchone()
    return dict(row)


def list_schedules(enabled_only: bool = False) -> list[dict]:
    from majestic.db.state import StateDB
    q = "SELECT * FROM schedules"
    if enabled_only:
        q += " WHERE enabled = 1"
    q += " ORDER BY id"
    rows = StateDB()._conn.execute(q).fetchall()
    return [dict(r) for r in rows]


def remove_schedule(schedule_id: int) -> bool:
    from majestic.db.state import StateDB
    db = StateDB()
    cur = db._conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
    db._conn.commit()
    return cur.rowcount > 0


def set_enabled(schedule_id: int, enabled: bool) -> None:
    from majestic.db.state import StateDB
    db = StateDB()
    db._conn.execute(
        "UPDATE schedules SET enabled = ? WHERE id = ?",
        (1 if enabled else 0, schedule_id),
    )
    db._conn.commit()


def get_due(now: Optional[datetime] = None) -> list[dict]:
    """Return enabled schedules whose next_run is <= now."""
    from majestic.db.state import StateDB
    ts = (now or datetime.now()).isoformat()
    rows = StateDB()._conn.execute(
        "SELECT * FROM schedules WHERE enabled = 1 AND next_run <= ? ORDER BY next_run",
        (ts,),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_ran(schedule_id: int) -> None:
    """Update last_run to now and compute next next_run."""
    from majestic.db.state import StateDB
    from croniter import croniter

    db = StateDB()
    row = db._conn.execute(
        "SELECT cron_expr FROM schedules WHERE id = ?", (schedule_id,)
    ).fetchone()
    if not row:
        return

    now = datetime.now()
    try:
        next_run = croniter(row["cron_expr"], now).get_next(datetime).isoformat()
    except Exception:
        next_run = None

    db._conn.execute(
        "UPDATE schedules SET last_run = ?, next_run = ? WHERE id = ?",
        (now.isoformat(), next_run, schedule_id),
    )
    db._conn.commit()


# ── Natural language → schedule ───────────────────────────────────────────────

_NL_PROMPT = """\
Convert this natural language schedule request into a JSON object.

Request: "{text}"

Return JSON with these fields:
- "name": short identifier (kebab-case, e.g. "daily-briefing")
- "cron": valid cron expression (5 fields: min hour dom mon dow)
- "prompt": what the agent should do (the task part of the request)
- "target": delivery target — "telegram" if mentioned, otherwise "cli"

Examples:
  "every day at 9am do a briefing" → {{"name":"daily-briefing","cron":"0 9 * * *","prompt":"generate briefing","target":"cli"}}
  "every monday at 8am research and send to telegram" → {{"name":"monday-research","cron":"0 8 * * 1","prompt":"run research","target":"telegram"}}
  "every 6 hours check market" → {{"name":"market-check","cron":"0 */6 * * *","prompt":"get market data","target":"cli"}}

Respond ONLY with JSON, no explanation.\
"""


def nl_to_schedule(text: str) -> dict:
    """Use LLM to parse natural language into {name, cron, prompt, target}."""
    import json
    from majestic.llm import get_provider

    prompt = _NL_PROMPT.format(text=text.strip())
    resp = get_provider().complete([{"role": "user", "content": prompt}])
    raw = resp.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()
    return json.loads(raw)
