"""Token usage commands (/usage, /insights) and session exit cleanup."""
from majestic.cli.display import G, Y, DIM, R


def cmd_exit(session_id, history: list, session_start_tokens: dict) -> None:
    """Run exit cleanup: memory dedup, nudge, session summary, DB close, Ollama shutdown."""
    if history:
        try:
            from majestic.memory.nudge import nudge_after_session
            from majestic import config as _cfg
            print(f"  {DIM}Saving session memory...{R}")
            nudge_after_session(history, lang=_cfg.get("language", "EN"), blocking=True)
        except Exception:
            pass
        try:
            from majestic.memory.dedup import dedup_memory
            if dedup_memory():
                print(f"  {DIM}Memory deduplicated.{R}")
        except Exception:
            pass
    if session_id:
        try:
            from majestic.memory.session_summarizer import summarize_session
            summarize_session(session_id)
        except Exception:
            pass
    if session_id:
        try:
            from majestic.db.state import StateDB
            from majestic.token_tracker import get_stats
            end  = get_stats()
            tin  = max(0, end.get("tokens_in",  0) - session_start_tokens.get("tokens_in",  0))
            tout = max(0, end.get("tokens_out", 0) - session_start_tokens.get("tokens_out", 0))
            cost = max(0.0, end.get("cost_usd", 0.0) - session_start_tokens.get("cost_usd", 0.0))
            StateDB().close_session(session_id, tin, tout, cost, len(history) * 2)
        except Exception:
            pass
    try:
        from majestic.llm.ollama import shutdown_ollama
        shutdown_ollama()
    except Exception:
        pass
    print(f"{DIM}Bye!{R}")


def cmd_usage(reset: bool = False) -> None:
    try:
        from majestic.token_tracker import get_stats, reset_stats
        if reset:
            reset_stats()
            print(f"  {G}✓ Token counter reset.{R}\n")
            return
        from rich.console import Console
        from rich.table import Table
        s = get_stats()
        t = Table(box=None, show_header=False, padding=(0, 2, 0, 2))
        t.add_column(style="dim", min_width=16)
        t.add_column()
        t.add_row("Input tokens",  f"{s.get('tokens_in',  0):,}")
        t.add_row("Output tokens", f"{s.get('tokens_out', 0):,}")
        cwrite = s.get("cache_write", 0)
        cread  = s.get("cache_read",  0)
        if cwrite or cread:
            t.add_row("Cache write",  f"{cwrite:,}")
            t.add_row("Cache read",   f"{cread:,}")
        t.add_row("Total cost",    f"[bold]${s.get('cost_usd', 0.0):.4f}[/]")
        t.add_row("Since",         s.get("reset_date", "—"))
        Console().print()
        Console().print(t)
        Console().print()
    except Exception as e:
        print(f"  {Y}Usage unavailable: {e}{R}\n")


def cmd_insights(rest: str = "") -> None:
    try:
        import json
        from datetime import datetime, timedelta
        from rich.console import Console
        from rich.table import Table
        from majestic.constants import MAJESTIC_HOME
        tokens_file = MAJESTIC_HOME / "tokens.json"
        if not tokens_file.exists():
            print(f"  {DIM}No usage data yet.{R}\n")
            return
        days = 7
        for part in rest.split():
            if part.lstrip("-").isdigit():
                days = max(1, int(part.lstrip("-")))
                break
        data    = json.loads(tokens_file.read_text(encoding="utf-8"))
        history = data.get("history", [])
        cutoff  = datetime.now() - timedelta(days=days)
        by_day: dict[str, dict] = {}
        for e in history:
            try:
                dt = datetime.fromisoformat(e["ts"])
                if dt < cutoff:
                    continue
                day = dt.strftime("%Y-%m-%d")
                rec = by_day.setdefault(day, {"in": 0, "out": 0, "cost": 0.0, "ops": 0})
                rec["in"]   += e.get("in", 0)
                rec["out"]  += e.get("out", 0)
                rec["cost"] += e.get("cost", 0.0)
                rec["ops"]  += 1
            except Exception:
                pass
        if not by_day:
            print(f"  {DIM}No activity in the last {days} day(s).{R}\n")
            return
        console = Console()
        t = Table(title=f"Last {days} days", box=None, padding=(0, 2, 0, 2))
        t.add_column("Date",  style="dim")
        t.add_column("In",    justify="right")
        t.add_column("Out",   justify="right")
        t.add_column("Ops",   justify="right")
        t.add_column("Cost",  justify="right")
        for day in sorted(by_day, reverse=True):
            r = by_day[day]
            t.add_row(day, f"{r['in']:,}", f"{r['out']:,}",
                      str(r['ops']), f"${r['cost']:.4f}")
        console.print()
        console.print(t)
        console.print()
    except Exception as e:
        print(f"  {Y}Insights unavailable: {e}{R}\n")
