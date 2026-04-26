"""
Interactive CLI REPL for the Majestic agent.

  Free text → AgentLoop
  /cmd       → commands.dispatch() or management handler
  /stop      → interrupt current agent task
  /exit      → memory nudge + DB session close
"""
from __future__ import annotations

from majestic.cli.display import R, B, C, G, Y, DIM, print_startup
from majestic.cli.repl_helpers import (
    _agent_stop,
    run_agent, dispatch_shortcut,
    looks_like_path, split_paths, handle_files,
)
from majestic.cli.repl_commands import (
    cmd_schedule, cmd_memory, cmd_forget, cmd_skills,
    cmd_remind, cmd_rss, cmd_reports, cmd_set, cmd_history,
    cmd_workspace,
)

_HELP = f"""
{B}Agent:{R}
  Type any question             → agent with tools
  /research                     → collect intel from all sources
  /briefing [days]              → market/tech briefing (default 14)
  /market                       → crypto, stocks, forex snapshot
  /news [N]                     → latest news (default 10)
  /report <topic>               → deep report on a topic
  /ideas                        → business ideas from recent trends
  Drag & drop or paste a path   → index .pdf .docx .csv .txt .md

{B}Memory & skills:{R}
  /workspace [view|search|del|move|mkdir] → manage workspace files
  /memory                       → view persistent memory
  /forget <topic>               → remove memory entries
  /skills                       → list saved skills
  /history [query | last N]     → search past conversations

{B}Management:{R}
  /model                        → switch LLM provider/model
  /set [key] [value]            → configure agent role and tools
  /usage [reset]                → token usage and cost
  /stop                         → stop current task
  /schedule [list|add|remove]   → manage cron schedules
  /remind <text>                → add reminder
  /reminders                    → list active reminders
  /rss [list|add|remove]        → manage RSS feeds
  /reports [view|del] <N>       → manage saved reports
  /help                         → this help
  /exit                         → quit
"""


def run() -> None:
    print_startup()

    try:
        from majestic.cron.scheduler import start_scheduler
        start_scheduler(delivery={"cli": print})
    except Exception:
        pass

    try:
        from majestic.memory.store import load_both
        if load_both():
            print(f"  {DIM}Memory loaded.{R}\n")
    except Exception:
        pass

    session_id: str | None = None
    session_start_tokens: dict = {}
    try:
        from majestic.db.state import StateDB
        from majestic import config as _cfg
        label = f"{_cfg.get('llm.provider')}/{_cfg.get('llm.model')}"
        session_id = StateDB().create_session(source="cli", model=label)
        try:
            from majestic.token_tracker import get_stats
            session_start_tokens = get_stats()
        except Exception:
            pass
    except Exception:
        pass

    from majestic.cli.commands import SHORTCUTS
    from majestic.skills.loader import list_skills

    history: list[tuple[str, str]] = []

    def _skill_names() -> set[str]:
        return {s["name"] for s in list_skills()}

    def _push(user: str, ans: str) -> None:
        history.append((user, ans))
        if len(history) > 10:
            history[:] = history[-10:]

    # ── Prompt setup (prompt_toolkit with tab-completion + toolbar) ───────────
    _pt_prompt = None
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import Completer, Completion
        from prompt_toolkit.formatted_text import FormattedText, HTML
        from prompt_toolkit.shortcuts.prompt import CompleteStyle
        from prompt_toolkit.styles import Style as PTStyle

        _STYLE = PTStyle.from_dict({
            "completion-menu":                    "bg:default noreverse",
            "completion-menu.completion":         "bg:default fg:#666677 nounderline noreverse",
            "completion-menu.completion.current": "bg:default fg:#D95767 bold nounderline noreverse",
            "scrollbar.background":               "bg:default",
            "scrollbar.button":                   "bg:default",
            "bottom-toolbar":                     "bg:default fg:#444455 noreverse",
        })

        _PROMPT_MSG = FormattedText([("", "  "), ("fg:#D95767 bold", "majestic ▶ ")])

        _STATIC_CMDS = [
            "/help", "/research", "/briefing", "/market", "/news", "/report",
            "/ideas", "/memory", "/forget", "/skills", "/model", "/usage",
            "/schedule", "/remind", "/reminders", "/rss", "/reports",
            "/history", "/set", "/workspace", "/stop", "/exit",
        ]

        class _SlashCompleter(Completer):
            def __init__(self, cmds: list[str]) -> None:
                self._cmds = cmds

            def get_completions(self, document, complete_event):
                word = document.get_word_before_cursor(WORD=True)
                if not word.startswith("/"):
                    return
                lo = word.lower()
                for cmd in self._cmds:
                    if cmd.lower().startswith(lo):
                        yield Completion(cmd, start_position=-len(word))

        def _make_completer():
            cmds = _STATIC_CMDS + [f"/{n}" for n in _skill_names()]
            return _SlashCompleter(cmds)

        def _toolbar():
            try:
                from majestic.token_tracker import get_stats
                s    = get_stats()
                cost = f"${s.get('cost_usd', 0.0):.4f}"
                tok  = s.get('tokens_in', 0) + s.get('tokens_out', 0)
                return HTML(f' <b>♛</b> <ansidarkgray>{label}  │  {tok:,} tok  │  {cost}  │  Tab for commands</ansidarkgray>')
            except Exception:
                return HTML(f' <b>♛</b> <ansidarkgray>{label}  │  Tab for commands</ansidarkgray>')

        _pt_prompt = PromptSession(
            completer=_make_completer(),
            complete_while_typing=True,
            complete_style=CompleteStyle.MULTI_COLUMN,
            bottom_toolbar=_toolbar,
            refresh_interval=2,
            style=_STYLE,
        )
    except Exception:
        pass

    def _get_input() -> str:
        if _pt_prompt is not None:
            _pt_prompt.completer = _make_completer()
            return _pt_prompt.prompt(_PROMPT_MSG).strip()
        import readline  # noqa: F401
        return input(f"  {C}majestic ▶ {R}").strip()

    while True:
        try:
            user = _get_input()
        except (EOFError, KeyboardInterrupt):
            print()
            user = "/exit"

        if not user:
            continue

        # ── Exit ──────────────────────────────────────────────────────────────
        if user.lower() in ("/exit", "/quit", "exit", "quit"):
            if history:
                try:
                    from majestic.memory.nudge import nudge_after_session
                    from majestic import config as _cfg
                    print(f"  {DIM}Saving session memory...{R}")
                    nudge_after_session(history, lang=_cfg.get("language", "EN"), blocking=True)
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
                    end = get_stats()
                    tin  = max(0, end.get("tokens_in", 0)  - session_start_tokens.get("tokens_in", 0))
                    tout = max(0, end.get("tokens_out", 0) - session_start_tokens.get("tokens_out", 0))
                    cost = max(0.0, end.get("cost_usd", 0.0) - session_start_tokens.get("cost_usd", 0.0))
                    StateDB().close_session(session_id, tin, tout, cost, len(history) * 2)
                except Exception:
                    pass
            print(f"{DIM}Bye!{R}")
            break

        elif user == "/help":
            print(_HELP)

        elif user == "/stop":
            _agent_stop.set()
            print(f"  {Y}Stop signal sent.{R}\n")

        # ── Tool shortcuts ────────────────────────────────────────────────────
        elif user.startswith("/") and user[1:].split()[0].lower() in SHORTCUTS:
            cmd  = user[1:].split()[0].lower()
            rest = user[1 + len(cmd):].strip()
            dispatch_shortcut(cmd, rest)

        elif user == "/model":
            try:
                from majestic.cli.setup import select_model
                select_model()
                print(f"  {G}✓ Model switched.{R}\n")
            except Exception as e:
                print(f"  {Y}Error: {e}{R}\n")

        elif user.startswith("/usage"):
            try:
                from majestic.token_tracker import get_stats, reset_stats
                if "reset" in user:
                    reset_stats()
                    print(f"  {G}✓ Token counter reset.{R}\n")
                else:
                    s = get_stats()
                    print(f"\n  {B}Token usage{R}\n"
                          f"  In:   {s.get('tokens_in', 0):,}\n"
                          f"  Out:  {s.get('tokens_out', 0):,}\n"
                          f"  Cost: ${s.get('cost_usd', 0.0):.4f}\n")
            except Exception as e:
                print(f"  {Y}Usage unavailable: {e}{R}\n")

        elif user == "/memory":
            cmd_memory()

        elif user.lower().startswith("/forget"):
            cmd_forget(user[7:].strip())

        elif user == "/skills":
            cmd_skills()

        elif user.lower().startswith("/schedule"):
            cmd_schedule(user[9:].strip())

        elif user.lower() == "/reminders":
            cmd_remind("", is_list=True)

        elif user.lower().startswith("/remind"):
            cmd_remind(user[7:].strip())

        elif user.lower().startswith("/rss"):
            cmd_rss(user[4:].strip())

        elif user.lower().startswith("/reports"):
            cmd_reports(user[8:].strip())

        elif user.lower().startswith("/history"):
            cmd_history(user[8:].strip())

        elif user.lower().startswith("/set"):
            cmd_set(user[4:].strip())

        elif user.lower().startswith("/workspace"):
            cmd_workspace(user[10:].strip())

        # ── Unknown slash or skill invocation ─────────────────────────────────
        elif user.startswith("/"):
            cmd  = user[1:].split()[0].lower()
            sarg = user[1 + len(cmd):].strip()
            if cmd in _skill_names():
                from majestic.skills.loader import load_skill, increment_usage
                skill = load_skill(cmd)
                if skill:
                    increment_usage(cmd)
                    prompt = f"Use skill '{cmd}':\n{skill['body']}"
                    if sarg:
                        prompt += f"\n\nUser input: {sarg}"
                    ans = run_agent(prompt, session_id, history)
                    if ans:
                        _push(user, ans)
            else:
                print(f"  {Y}Unknown command. Type /help{R}\n")

        # ── File drag & drop ──────────────────────────────────────────────────
        elif looks_like_path(user):
            paths = split_paths(user)
            if paths:
                handle_files(paths)
            else:
                ans = run_agent(user, session_id, history)
                if ans:
                    _push(user, ans)

        # ── Free text → AgentLoop ─────────────────────────────────────────────
        else:
            ans = run_agent(user, session_id, history)
            if ans:
                _push(user, ans)
