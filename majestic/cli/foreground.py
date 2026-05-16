import asyncio
import time


def run(profile_name: str = "default", tui: bool = False):
    """Run agent in foreground mode — plain CLI by default, TUI with --tui."""
    if tui:
        try:
            from majestic.cli.tui.app import MajesticApp
        except ImportError:
            import majestic.display as display
            display.warn("textual not installed — falling back to plain mode.")
            display.info("Install with: pip install textual")
            asyncio.run(_run_plain(profile_name))
            return
        app = MajesticApp(profile_name)
        app.run()
    else:
        asyncio.run(_run_plain(profile_name))


async def _run_plain(profile_name: str):
    from majestic.config.settings import Settings
    from majestic.memory.working import WorkingMemory
    from majestic.core.gateway import Gateway
    from majestic.channels.cli import CLIChannel
    from majestic.core.runtime import AgentRuntime
    from majestic.llm.router import LLMRouter
    from majestic.system.startup import StartupManager
    from majestic import display
    import uuid

    settings = Settings(profile_name)
    settings.validate()

    session_id = str(uuid.uuid4())[:8]
    working_memory = WorkingMemory()
    channel = CLIChannel(session_id=session_id)
    llm_router = LLMRouter(settings)

    startup = StartupManager(settings)
    incomplete = await startup.run()

    if incomplete:
        display.warn(f"{len(incomplete)} incomplete task(s) found — will resume on next run.")

    display.print_startup(profile_name, "foreground")

    # Register profile skills as slash-command completions
    try:
        from majestic.memory.procedural import ProceduralMemory
        pm = ProceduralMemory(str(settings.skills_dir))
        channel.set_skill_completions([s.get("name", "") for s in pm.get_all()])
    except Exception:
        pass

    gateway = Gateway(settings, working_memory, channel)
    system_prompt = gateway.build_system_prompt()

    runtime = _build_runtime(settings, working_memory, llm_router)
    runtime = _register_tools(runtime, settings)

    _last_stats: dict | None = None

    while True:
        try:
            raw = await channel.receive()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        text = raw.get("text", "").strip()
        if not text:
            continue
        if text.lower() in ("/exit", "/quit", "exit", "quit"):
            display.ok("Goodbye!")
            break

        if text.startswith("/"):
            slash_result = await _handle_slash_plain(text, profile_name, working_memory, runtime, settings)
            if slash_result is True:
                continue
            elif isinstance(slash_result, str):
                text = slash_result  # skill expanded to task

        # Show previous task stats right below the user's input line
        if _last_stats:
            display.inline_stats(**_last_stats)

        working_memory.add_message("user", text)
        print()

        t0 = time.monotonic()
        try:
            result = await runtime.run(
                task=text,
                system_prompt=system_prompt,
            )
        except Exception as exc:
            result = f"Error: {exc}"
        elapsed = time.monotonic() - t0

        _last_stats = {
            "tokens":  getattr(runtime, "_tokens_used", 0),
            "cost":    getattr(runtime, "_cost_used", 0.0),
            "elapsed": elapsed,
        }

        await channel.send(f"\n{result}\n")
        working_memory.add_message("assistant", result)


async def _handle_slash_plain(text: str, profile_name: str, working_memory, runtime, settings=None):
    """Handle a slash command in plain CLI.

    Returns:
        True  — handled, skip to next message.
        str   — skill expanded to a task string; caller runs it through runtime.
        False — not a known command, pass original text to agent.
    """
    try:
        from rich.console import Console
        console = Console()
    except ImportError:
        console = None

    def out(markup: str) -> None:
        if console:
            console.print(markup)
        else:
            print(markup)

    cmd = text.strip().lower().split()[0]

    if cmd == "/help":
        from majestic.cli.tui.commands import SLASH_COMMANDS
        out("[bold]Available commands:[/bold]")
        for c, desc in SLASH_COMMANDS.items():
            out(f"  [cyan]{c:<10}[/cyan]  [dim]{desc}[/dim]")
        return True

    if cmd == "/skills":
        try:
            from majestic.display import _gather_startup
            d = _gather_startup(profile_name)
            skills = d.get("skills", [])
            if not skills:
                out("[dim]No skills loaded yet. Add YAML files to profiles/<name>/skills/[/dim]")
            else:
                out("[bold]Loaded skills:[/bold]")
                for sk in skills:
                    name = sk.get("name", "?")
                    raw  = sk.get("description", "")
                    desc = (raw[:57] + "…") if len(raw) > 60 else raw
                    out(f"  [cyan]/{name:<18}[/cyan] [dim]{desc}[/dim]")
        except Exception as e:
            out(f"[red]Error: {e}[/red]")
        return True

    if cmd == "/tools":
        tools = list(getattr(runtime, "tools", {}).keys())
        if not tools:
            out("[dim]No tools registered.[/dim]")
        else:
            out("[bold]Available tools:[/bold]")
            for t in tools:
                out(f"  [cyan]{t}[/cyan]")
        return True

    if cmd == "/research":
        words = text.strip().split(None, 1)
        query = words[1].strip() if len(words) > 1 else ""
        if not query:
            out("[dim]Usage: /research <query>  e.g. /research AI news[/dim]")
            return True
        out(f"[dim]Fetching from curated sources…[/dim]")
        try:
            from majestic.tools.research import research as _research
            result = await _research(query)
        except Exception as e:
            out(f"[red]Error: {e}[/red]")
            return True
        items = result.get("results", [])
        ok    = result.get("sources_ok", [])
        failed = result.get("sources_failed", [])
        if not items:
            out(f"[dim]No results found for:[/dim] {query}")
            if failed:
                out(f"[dim]Failed sources: {', '.join(failed)}[/dim]")
            return True
        out(f"\n[bold]Research:[/bold] {query}  [dim]· {len(items)} results from {len(ok)} sources[/dim]\n")
        _cat_seen: set[str] = set()
        for item in items:
            cat = item.get("category", "")
            if cat not in _cat_seen:
                out(f"[dim]── {cat.upper()} ──[/dim]")
                _cat_seen.add(cat)
            date    = f"[dim]{item['date']}[/dim]  " if item.get("date") else ""
            source  = f"[dim]{item['source']}[/dim]"
            title   = item.get("title", "")
            summary = item.get("summary", "")
            url     = item.get("url", "")
            out(f"{date}{source}")
            out(f"  [bold]{title}[/bold]")
            if summary:
                out(f"  [dim]{summary[:120]}[/dim]")
            if url:
                out(f"  [cyan]{url}[/cyan]")
            out("")
        if failed:
            out(f"[dim]Unavailable: {', '.join(failed)}[/dim]")
        return True

    if cmd == "/agents":
        try:
            import json
            from pathlib import Path
            reg = Path(__file__).resolve().parent.parent.parent / "data" / "registry.json"
            if not reg.exists():
                out("[dim]No background agents running. Start one with: majestic run <profile>[/dim]")
            else:
                data = json.loads(reg.read_text())
                if not data:
                    out("[dim]No background agents running. Start one with: majestic run <profile>[/dim]")
                else:
                    out("[bold]Running agents:[/bold]")
                    for name, info in data.items():
                        port = info.get("port", "?")
                        status = info.get("status", "?")
                        dot = "[green]●[/green]" if status == "running" else "[yellow]●[/yellow]"
                        out(f"  {dot} [bold]{name}[/bold]  [dim]:{port}  {status}[/dim]")
        except Exception as e:
            out(f"[red]Error: {e}[/red]")
        return True

    if cmd == "/memory":
        try:
            from majestic.display import _gather_startup
            d = _gather_startup(profile_name)
            mem = d.get("mem_count", 0)
            les = d.get("lessons_count", 0)
            out(
                f"[bold]Memory:[/bold]\n"
                f"  [dim]episodic · [/dim]{mem} tasks\n"
                f"  [dim]lessons  · [/dim]{les}\n"
                f"  [dim]semantic · [/dim]sqlite-vec"
            )
        except Exception as e:
            out(f"[red]Error: {e}[/red]")
        return True

    if cmd == "/budget":
        tokens = getattr(runtime, "_tokens_used", 0)
        cost = getattr(runtime, "_cost_used", 0.0)
        out(
            f"[bold]Budget:[/bold]\n"
            f"  [dim]tokens · [/dim]{tokens:,}\n"
            f"  [dim]cost   · [/dim]${cost:.4f}"
        )
        return True

    if cmd == "/new":
        working_memory.clear()
        out("[dim]Session cleared.[/dim]")
        return True

    # Skill invocation: /skill_name [optional user input]
    if settings is not None:
        try:
            from majestic.memory.procedural import ProceduralMemory
            pm = ProceduralMemory(str(settings.skills_dir))
            skill_map = {s.get("name", ""): s for s in pm.get_all()}
            cmd_name = cmd.lstrip("/")
            if cmd_name in skill_map:
                skill = skill_map[cmd_name]
                words = text.strip().split(None, 1)
                user_input = words[1].strip() if len(words) > 1 else ""
                lines = [skill.get("description", skill["name"])]
                steps = skill.get("steps", [])
                if steps:
                    lines.append("\nFollow these steps:")
                    lines.extend(f"  - {s}" for s in steps)
                if user_input:
                    lines.append(f"\nUser input: {user_input}")
                out(f"[dim]Running skill:[/dim] [bold]{cmd_name}[/bold]")
                return "\n".join(lines)
        except Exception:
            pass

    return False


def _build_runtime(settings, working_memory, llm_router) -> "AgentRuntime":
    """Instantiate AgentRuntime with the full self-evolution stack wired up."""
    from majestic.core.runtime import AgentRuntime
    from majestic.memory.lessons import LessonsStore
    from majestic.memory.episodic import EpisodicMemory
    from majestic.memory.checkpoints import CheckpointStore
    from majestic.core.script_tracker import ScriptTracker
    from majestic.core.skill_writer import SkillWriter
    from majestic.core.self_evolution import SelfEvolution
    from majestic.core.reflection import ReflectionEngine
    from majestic.core.planner import Planner

    data_dir   = settings.data_dir
    skills_dir = settings.skills_dir
    workspace  = settings.workspace_dir

    lessons_store   = LessonsStore(str(data_dir / "lessons.db"))
    episodic_memory = EpisodicMemory(str(data_dir / "episodic.db"))
    checkpoint_store = CheckpointStore(str(data_dir / "checkpoints.db"))
    script_tracker  = ScriptTracker(str(data_dir / "script_tracker.db"))

    skill_writer = SkillWriter(llm_router, str(skills_dir))
    evolution    = SelfEvolution(
        llm_router=llm_router,
        skill_writer=skill_writer,
        script_tracker=script_tracker,
        lessons_store=lessons_store,
        workspace_dir=str(workspace),
    )
    reflection_engine = ReflectionEngine(
        llm_router=llm_router,
        lessons_store=lessons_store,
        episodic_memory=episodic_memory,
        self_evolution=evolution,
    )
    planner = Planner(settings, llm_router, lessons_store)

    return AgentRuntime(
        settings=settings,
        working_memory=working_memory,
        llm_router=llm_router,
        checkpoint_store=checkpoint_store,
        reflection_engine=reflection_engine,
        planner=planner,
        hitl_enabled=False,
    )


def _register_tools(runtime, settings):
    workspace = settings.workspace_dir
    brave_key = settings.brave_search_api_key

    from majestic.tools.web_search.search import search as web_search_fn
    from majestic.tools.web_fetch import fetch as web_fetch_fn
    from majestic.tools.http import get as http_get, post as http_post
    from majestic.tools.files import FilesTool
    from majestic.tools.python_exec.executor import PythonExecutor
    from majestic.tools.node_exec.executor import NodeExecutor
    from majestic.tools.agent_client import AgentClient
    from majestic.tools.research import research as research_fn
    from majestic.core.script_tracker import ScriptTracker
    from pathlib import Path

    # Reuse the tracker wired into the reflection engine so counts persist
    script_tracker: ScriptTracker | None = None
    try:
        script_tracker = runtime._reflection.evolution.tracker
    except AttributeError:
        pass

    files     = FilesTool(workspace)
    py_exec   = PythonExecutor(str(settings.profile_dir), script_tracker=script_tracker)
    node_exec = NodeExecutor(str(settings.profile_dir),   script_tracker=script_tracker)
    agent_client = AgentClient()

    tools_dir = settings.tools_dir  # auto-creates workspace/tools/

    async def web_search_tool(query: str, max_results: int = 5):
        """Search the web for information."""
        return await web_search_fn(query, max_results, brave_api_key=brave_key)

    async def list_scripts() -> list[str]:
        """List reusable scripts in workspace/tools/. Always call before writing new code."""
        scripts = [p.name for p in sorted(tools_dir.iterdir()) if p.suffix in (".py", ".js")]
        return scripts if scripts else ["(no scripts yet)"]

    async def run_script(filename: str) -> str:
        """Run a saved script from workspace/tools/ by filename. Use list_scripts first."""
        script = tools_dir / filename
        if not script.exists():
            return f"Error: '{filename}' not found. Available: {[p.name for p in tools_dir.iterdir() if p.suffix in ('.py', '.js')]}"
        code = script.read_text(encoding="utf-8")
        if filename.endswith(".js"):
            return await node_exec.run(code)
        return await py_exec.run(code)

    async def delegate_to_agent(agent_name: str, task: str):
        """Delegate a task to a background agent (fire-and-forget — no result returned here)."""
        await agent_client.ensure_running(agent_name)
        resp = await agent_client.delegate(agent_name, task)
        return (
            f"Task accepted by agent '{agent_name}' (task_id={resp.get('task_id', '?')}). "
            "Processing in background — no result returned. Synthesize your answer now."
        )

    runtime.tools = {
        "web_search":        web_search_tool,
        "web_fetch":         web_fetch_fn,
        "http_get":          http_get,
        "http_post":         http_post,
        "file_read":         files.read,
        "file_write":        files.write,
        "file_list":         files.list,
        "python_exec":       py_exec.run,
        "node_exec":         node_exec.run,
        "list_scripts":      list_scripts,
        "run_script":        run_script,
        "research":          research_fn,
        "list_agents":       agent_client.list_profiles_with_roles,
        "delegate_to_agent": delegate_to_agent,
    }

    return runtime
