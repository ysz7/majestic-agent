"""CLI management command handlers — /set, /history, /schedule, /memory, /workspace, etc."""
from majestic.cli.display import R, B, C, G, Y, DIM, Spinner



def cmd_set(rest: str) -> None:
    from majestic import config as _cfg
    parts = rest.split(None, 1)
    if len(parts) < 2:
        cfg = _cfg.load()
        agent = cfg.get("agent", {})
        try:
            from majestic.tools.toolsets import current_toolset
            ts = current_toolset() or "(custom)"
        except Exception:
            ts = "—"
        print(f"\n  {B}agent.role{R}          {DIM}{agent.get('role', '') or '(none)'}{R}")
        print(f"  {B}agent.toolset{R}       {DIM}{ts}{R}")
        print(f"  {B}agent.tools_enabled{R} {DIM}{agent.get('tools_enabled', []) or '(all)'}{R}")
        print(f"  {B}agent.tools_disabled{R}{DIM}{agent.get('tools_disabled', []) or '(none)'}{R}\n")
        print(f"  {DIM}Usage: /set <key> <value>{R}")
        print(f"  {DIM}Keys: agent.role, toolset, agent.tools_enabled, agent.tools_disabled{R}\n")
        return

    key, val_str = parts[0], parts[1]

    # /set toolset <name>
    if key == "toolset":
        try:
            from majestic.tools.toolsets import apply_toolset, list_toolsets
            if apply_toolset(val_str.strip()):
                print(f"  {G}✓ Toolset → {val_str.strip()}{R}\n")
            else:
                available = ", ".join(list_toolsets().keys())
                print(f"  {Y}Unknown toolset. Available: {available}{R}\n")
        except Exception as e:
            print(f"  {Y}Error: {e}{R}\n")
        return

    if key in ("agent.tools_enabled", "agent.tools_disabled"):
        val = [v.strip() for v in val_str.split(",") if v.strip()] if val_str.strip() != "-" else []
    else:
        val = val_str if val_str.strip() != "-" else ""
    _cfg.set_value(key, val)
    print(f"  {G}✓ {key} = {val!r}{R}\n")


def cmd_history(rest: str) -> None:
    from majestic.db.state import StateDB
    db = StateDB()
    parts = rest.strip().split(None, 1)
    sub = parts[0].lower() if parts else "last"
    arg = parts[1] if len(parts) > 1 else ""

    if sub == "last" or not rest.strip():
        try:
            n = int(arg) if arg else 10
        except ValueError:
            n = 10
        rows = db.get_recent_sessions(limit=n)
        if not rows:
            print(f"  {DIM}No sessions found.{R}\n")
            return
        print()
        for r in rows:
            date  = (r.get("started_at") or "")[:16].replace("T", " ")
            title = r.get("title") or f"{DIM}(no summary){R}"
            msgs  = r.get("message_count", 0)
            print(f"  {DIM}{date}{R}  {title}  {DIM}{msgs} msgs{R}")
        print()
    else:
        query = rest.strip()
        if not query:
            print(f"  {Y}Usage: /history <query> | last [N]{R}\n")
            return
        with Spinner("Searching history..."):
            from majestic.tools.history_search import history_search
            result = history_search(query)
        from majestic.gateway.formatter import print_cli
        print_cli(result)


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
                par = f" {C}[parallel]{R}" if r.get("parallel") else ""
                print(f"  {dot} [{r['id']}] {r['name']:30s} {DIM}{r['cron_expr']}{R}{par}")
            print()
    elif sub == "add":
        if not arg:
            print(f"  {Y}Usage: /schedule add <description>{R}\n")
            return
        with Spinner("Parsing schedule..."):
            sched = nl_to_schedule(arg)
        add_schedule(
            name=sched["name"],
            cron_expr=sched["cron"],
            prompt=sched.get("prompt", ""),
            delivery_target=sched.get("target", "cli"),
            parallel=sched.get("parallel", False),
            subtasks=sched.get("subtasks"),
        )
        par_tag = f" {C}[parallel]{R}" if sched.get("parallel") else ""
        print(f"  {G}✓ Added:{R} {sched['name']} ({sched['cron']}){par_tag}\n")
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
        from majestic.gateway.formatter import print_cli
        print_cli(show())
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
    from majestic.skills.loader import list_user_skills
    skills = list_user_skills()
    if not skills:
        print(f"  {DIM}No user skills yet.{R}\n")
        return
    for s in skills:
        print(f"  {G}/{s['name']}{R}  {DIM}{s.get('description', '')}  (used {s.get('usage_count', 0)}x){R}")
    print()


def cmd_agent_skills() -> None:
    from majestic.skills.loader import list_agent_skills
    skills = list_agent_skills()
    if not skills:
        print(f"  {DIM}No agent-created skills yet.{R}\n")
        return
    print(f"\n  {DIM}Auto-created by agent:{R}")
    for s in skills:
        print(f"  {DIM}/{s['name']}{R}  {DIM}{s.get('description', '')}  (used {s.get('usage_count', 0)}x){R}")
    print()


def cmd_remind(rest: str, is_list: bool = False) -> None:
    if is_list or not rest:
        try:
            from majestic.reminders import list_reminders
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
            from majestic.reminders import add_reminder
            add_reminder(rest)
            print(f"  {G}✓ Reminder set.{R}\n")
        except Exception as e:
            print(f"  {Y}Error: {e}{R}\n")


def cmd_workspace(rest: str) -> None:
    from majestic.constants import WORKSPACE_DIR
    import sys as _sys
    from majestic.cli.repl_helpers import _LineSpinner
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    parts = rest.split(None, 1)
    sub   = parts[0].lower() if parts else ""
    arg   = parts[1] if len(parts) > 1 else ""
    if not sub:
        from majestic.tools.files.workspace import workspace_tree
        lines = workspace_tree(WORKSPACE_DIR)
        if not lines:
            print(f"  {DIM}Workspace is empty. ({WORKSPACE_DIR}){R}\n")
        else:
            print(f"\n  {B}workspace/{R}")
            for line in lines:
                print(f"  {line}")
            print()
        return
    if sub == "view":
        if not arg:
            print(f"  {Y}Usage: /workspace view <path>{R}\n")
            return
        from majestic.tools.files.workspace import _resolve, _read_any
        p = _resolve(arg)
        if not p.exists():
            print(f"  {Y}Not found: {arg}{R}\n")
            return
        if p.is_dir():
            from majestic.tools.files.workspace import workspace_tree
            print(f"\n  {B}{arg}/{R}")
            for line in workspace_tree(p):
                print(f"  {line}")
            print()
            return
        text = _read_any(p)
        print(f"\n  {B}{arg}{R}")
        from majestic.gateway.formatter import print_cli
        print_cli(text)

    elif sub == "search":
        if not arg:
            print(f"  {Y}Usage: /workspace search <query>{R}\n")
            return
        spinner = _LineSpinner(_sys.__stdout__)
        spinner.start(f" {DIM}├ Working [searching workspace · {arg[:30]}]{R}")
        from majestic.tools.files.workspace import workspace_search
        result = workspace_search(arg)
        spinner.stop()
        print(f"\n{result}\n")

    elif sub == "del":
        if not arg:
            print(f"  {Y}Usage: /workspace del <path>{R}\n")
            return
        confirm = input(f"  Delete '{arg}'? [y/N] ").strip().lower()
        if confirm != "y":
            print(f"  {DIM}Cancelled.{R}\n")
            return
        from majestic.tools.files.workspace import workspace_delete
        print(f"  {workspace_delete(arg)}\n")

    elif sub == "move":
        argv = arg.split(None, 1)
        if len(argv) < 2:
            print(f"  {Y}Usage: /workspace move <src> <dst>{R}\n")
            return
        from majestic.tools.files.workspace import workspace_move
        print(f"  {workspace_move(argv[0], argv[1])}\n")

    elif sub == "mkdir":
        if not arg:
            print(f"  {Y}Usage: /workspace mkdir <folder>{R}\n")
            return
        from majestic.tools.files.workspace import workspace_mkdir
        print(f"  {workspace_mkdir(arg)}\n")

    else:
        print(f"  {Y}Usage: /workspace [view|search|del|move|mkdir] ...{R}\n")


def cmd_rss(rest: str) -> None:
    try:
        from majestic.tools.web.rss import list_feeds, add_feed, remove_feed
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
            from majestic.gateway.formatter import print_cli
            print_cli(content)
        except (ValueError, IndexError):
            print(f"  {Y}Invalid report number.{R}\n")
    elif sub == "del":
        try:
            reports[int(arg) - 1].unlink()
            print(f"  {G}✓ Deleted.{R}\n")
        except (ValueError, IndexError):
            print(f"  {Y}Invalid report number.{R}\n")


