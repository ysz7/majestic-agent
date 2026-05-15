import asyncio


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

    gateway = Gateway(settings, working_memory, channel)
    system_prompt = gateway.build_system_prompt()

    runtime = AgentRuntime(settings, working_memory, llm_router)
    runtime = _register_tools(runtime, settings)

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
            if _handle_slash_plain(text, profile_name, working_memory, runtime):
                continue

        working_memory.add_message("user", text)
        print()

        try:
            result = await runtime.run(
                task=text,
                system_prompt=system_prompt,
            )
        except Exception as exc:
            result = f"Error: {exc}"

        await channel.send(f"\n{result}\n")
        working_memory.add_message("assistant", result)


def _handle_slash_plain(text: str, profile_name: str, working_memory, runtime) -> bool:
    """Handle a slash command in plain CLI. Returns True if handled, False to pass to agent."""
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
                    desc = sk.get("description", "")[:60]
                    out(f"  [cyan]/{name:<18}[/cyan] [dim]{desc}[/dim]")
        except Exception as e:
            out(f"[red]Error: {e}[/red]")
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

    return False


def _register_tools(runtime, settings):
    workspace = settings.workspace_dir
    brave_key = settings.brave_search_api_key

    from majestic.tools.web_search.search import search as web_search_fn, tool_schema as ws_schema
    from majestic.tools.web_fetch import fetch as web_fetch_fn, tool_schema as wf_schema
    from majestic.tools.http import get as http_get, post as http_post
    from majestic.tools.files import FilesTool
    from majestic.tools.python_exec.executor import PythonExecutor
    from majestic.tools.node_exec.executor import NodeExecutor
    from majestic.tools.agent_client import AgentClient

    files = FilesTool(workspace)
    py_exec = PythonExecutor(str(settings.profile_dir))
    node_exec = NodeExecutor(str(settings.profile_dir))
    agent_client = AgentClient()

    async def web_search_tool(query: str, max_results: int = 5):
        return await web_search_fn(query, max_results, brave_api_key=brave_key)

    async def delegate_to_agent(agent_name: str, task: str):
        """Auto-start the agent if needed, then delegate the task."""
        await agent_client.ensure_running(agent_name)
        return await agent_client.delegate(agent_name, task)

    runtime.tools = {
        "web_search": web_search_tool,
        "web_fetch": web_fetch_fn,
        "http_get": http_get,
        "http_post": http_post,
        "file_read": files.read,
        "file_write": files.write,
        "file_list": files.list,
        "python_exec": py_exec.run,
        "node_exec": node_exec.run,
        "list_agents": agent_client.list_profiles_with_roles,
        "delegate_to_agent": delegate_to_agent,
    }

    return runtime
