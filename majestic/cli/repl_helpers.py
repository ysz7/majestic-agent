"""
Helper functions for the CLI REPL: agent runner, command handlers, file ops.
Imported by repl.py to keep the main loop file under 300 lines.
"""
from __future__ import annotations

import re
import threading
from pathlib import Path

from majestic.cli.display import R, B, C, G, Y, DIM, Spinner

_agent_stop = threading.Event()

SUPPORTED_EXTS = {".pdf", ".docx", ".csv", ".txt", ".md"}

_TOOL_LABELS: dict[str, str] = {
    "search_knowledge":  "searching knowledge base",
    "search_web":        "searching web",
    "get_market_data":   "fetching market data",
    "run_research":      "collecting intel",
    "get_briefing":      "generating briefing",
    "get_news":          "fetching news",
    "get_report":        "generating report",
    "generate_ideas":    "generating ideas",
    "delegate_task":     "delegating sub-task",
    "delegate_parallel": "running parallel tasks",
    "read_file":         "reading file",
    "write_file":        "writing file",
    "run_command":       "running command",
}


# ── Agent runner ──────────────────────────────────────────────────────────────

def run_agent(user_input: str, session_id: str | None, history: list) -> str:
    from majestic.agent.loop import AgentLoop
    import sys as _sys

    _agent_stop.clear()
    _tools_used: list[str] = []

    def _on_tool(name: str, _args: dict) -> None:
        _tools_used.append(name)
        label = _TOOL_LABELS.get(name, name)
        _sys.__stdout__.write(f"\r\033[2K  {DIM}{label}...{R}\n")
        _sys.__stdout__.flush()

    loop = AgentLoop(stop_event=_agent_stop)
    try:
        with Spinner("Thinking..."):
            result = loop.run(
                user_input,
                session_id=session_id,
                history=history,
                on_tool_call=_on_tool,
            )
    except KeyboardInterrupt:
        _agent_stop.set()
        print(f"\n  {Y}Stopped.{R}\n")
        return ""

    _print_answer(result)
    answer = result.get("answer", "")

    if len(set(_tools_used)) >= 2 and answer:
        try:
            from majestic.skills.creator import suggest_skill
            from majestic import config as _cfg
            suggest_skill(user_input, answer[:500], _tools_used, lang=_cfg.get("language", "EN"))
        except Exception:
            pass

    return answer


def _print_answer(result: dict) -> None:
    try:
        from core.formatter import render_cli
        text = render_cli(result.get("answer", ""))
    except Exception:
        text = result.get("answer", "")
    print(f"\n{DIM}{'─' * 64}{R}\n{text}\n{DIM}{'─' * 64}{R}\n")


def dispatch_shortcut(cmd: str, rest: str) -> None:
    from majestic.cli.commands import dispatch
    args: dict = {}
    if cmd == "briefing" and rest:
        try:
            args["days"] = int(rest.split()[0])
        except ValueError:
            pass
    elif cmd == "news" and rest:
        try:
            args["limit"] = int(rest.split()[0])
        except ValueError:
            pass
    elif cmd == "report":
        args["topic"] = rest
    with Spinner(f"/{cmd}..."):
        result = dispatch(cmd, args)
    try:
        from core.formatter import render_cli
        print(f"\n{render_cli(result)}\n")
    except Exception:
        print(f"\n{result}\n")


# ── File handling ─────────────────────────────────────────────────────────────

def looks_like_path(text: str) -> bool:
    return len(split_paths(text.strip())) > 0


def split_paths(text: str) -> list[Path]:
    tokens = re.findall(r'"[^"]*"|\'[^\']*\'|\S+', text)
    paths = []
    for token in tokens:
        p = Path(token.strip("'\"").replace("\\", "/")).expanduser()
        if p.exists() and p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            paths.append(p)
    return paths


def handle_files(paths: list[Path]) -> None:
    import majestic.tools as _tools
    for p in paths:
        size_kb = p.stat().st_size / 1024
        size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb / 1024:.1f} MB"
        print(f"\n  📄 {p.name} ({size_str}) — index? [Enter / n] ", end="", flush=True)
        if input().strip().lower() == "n":
            continue
        with Spinner(f"Indexing {p.name}..."):
            _tools.execute("index_file", {"path": str(p)})
        print(f"  {G}✓ Indexed {p.name}{R}\n")


# ── Management command handlers ───────────────────────────────────────────────

def cmd_schedule(rest: str) -> None:
    from majestic.cron.jobs import list_schedules, add_schedule, remove_schedule, nl_to_schedule
    parts = rest.split(None, 1)
    sub   = parts[0].lower() if parts else "list"
    arg   = parts[1] if len(parts) > 1 else ""

    if not sub or sub == "list":
        rows = list_schedules()
        if not rows:
            print(f"  {DIM}No schedules.{R}\n")
        else:
            for r in rows:
                dot = f"{G}●{R}" if r.get("enabled") else f"{DIM}○{R}"
                print(f"  {dot} [{r['id']}] {r['name']:30s} {DIM}{r['cron']}{R}")
            print()
    elif sub == "add":
        if not arg:
            print(f"  {Y}Usage: /schedule add <description>{R}\n")
            return
        with Spinner("Parsing schedule..."):
            sched = nl_to_schedule(arg)
        add_schedule(**sched)
        print(f"  {G}✓ Added:{R} {sched['name']} ({sched['cron']})\n")
    elif sub == "remove":
        try:
            remove_schedule(int(arg))
            print(f"  {G}✓ Removed schedule {arg}{R}\n")
        except (ValueError, Exception) as e:
            print(f"  {Y}Error: {e}{R}\n")
    else:
        print(f"  {Y}Usage: /schedule [list|add|remove]{R}\n")


def cmd_memory() -> None:
    try:
        from majestic.memory.store import show
        try:
            from core.formatter import render_cli
            print(f"\n{render_cli(show())}\n")
        except Exception:
            print(f"\n{show()}\n")
    except Exception as e:
        print(f"  {Y}Memory unavailable: {e}{R}\n")


def cmd_forget(topic: str) -> None:
    if not topic:
        print(f"  {Y}Usage: /forget <topic>{R}\n")
        return
    try:
        from majestic.memory.store import forget
        n = forget(topic)
        if n:
            print(f"  {G}✓ Removed {n} entr{'y' if n == 1 else 'ies'} mentioning «{topic}»{R}\n")
        else:
            print(f"  {DIM}Nothing found mentioning «{topic}»{R}\n")
    except Exception as e:
        print(f"  {Y}Error: {e}{R}\n")


def cmd_skills() -> None:
    from majestic.skills.loader import list_skills
    skills = list_skills()
    if not skills:
        print(f"  {DIM}No skills saved yet.{R}\n")
        return
    for s in skills:
        print(f"  {G}/{s['name']}{R}  {DIM}{s.get('description', '')}  (used {s.get('usage_count', 0)}x){R}")
    print()


def cmd_remind(rest: str, is_list: bool = False) -> None:
    if is_list or not rest:
        try:
            from core.reminders import list_reminders
            rows = list_reminders()
            if not rows:
                print(f"  {DIM}No active reminders.{R}\n")
            else:
                for r in rows:
                    print(f"  {DIM}{r['dt'][:16]}{R}  {r['text']}")
                print()
        except Exception as e:
            print(f"  {Y}Error: {e}{R}\n")
    else:
        try:
            from core.reminders import add_reminder
            add_reminder(rest)
            print(f"  {G}✓ Reminder set.{R}\n")
        except Exception as e:
            print(f"  {Y}Error: {e}{R}\n")


def cmd_rss(rest: str) -> None:
    try:
        from core.rss import list_feeds, add_feed, remove_feed
        parts = rest.split(None, 1)
        sub   = parts[0].lower() if parts else "list"
        arg   = parts[1] if len(parts) > 1 else ""
        if sub == "add":
            add_feed(arg)
            print(f"  {G}✓ Feed added.{R}\n")
        elif sub == "remove":
            remove_feed(int(arg))
            print(f"  {G}✓ Feed removed.{R}\n")
        else:
            feeds = list_feeds()
            if not feeds:
                print(f"  {DIM}No RSS feeds configured.{R}\n")
            else:
                for i, f in enumerate(feeds, 1):
                    print(f"  {i}. {f.get('url', f)}")
                print()
    except Exception as e:
        print(f"  {Y}Error: {e}{R}\n")


def cmd_reports(rest: str) -> None:
    from majestic.constants import EXPORTS_DIR
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    reports = sorted(EXPORTS_DIR.glob("*.md"))
    parts = rest.split(None, 1)
    sub   = parts[0].lower() if parts else ""
    arg   = parts[1] if len(parts) > 1 else ""

    if not sub:
        if not reports:
            print(f"  {DIM}No reports saved.{R}\n")
        else:
            for i, p in enumerate(reports, 1):
                print(f"  {i}. {p.stem}")
            print()
    elif sub == "view":
        try:
            content = reports[int(arg) - 1].read_text(encoding="utf-8")
            try:
                from core.formatter import render_cli
                print(render_cli(content))
            except Exception:
                print(content)
        except (ValueError, IndexError):
            print(f"  {Y}Invalid report number.{R}\n")
    elif sub == "del":
        try:
            reports[int(arg) - 1].unlink()
            print(f"  {G}✓ Deleted.{R}\n")
        except (ValueError, IndexError):
            print(f"  {Y}Invalid report number.{R}\n")
