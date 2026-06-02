import asyncio
import sys
import time


def run(profile_name: str = "default"):
    """Run agent in foreground mode (interactive CLI)."""
    asyncio.run(_run_plain(profile_name))


async def _run_plain(profile_name: str):
    from majestic.config.settings import Settings
    from majestic.core.gateway import Gateway
    from majestic.channels.cli import CLIChannel
    from majestic.core.runtime import AgentRuntime
    from majestic.llm.router import LLMRouter
    from majestic.system.startup import StartupManager
    from majestic import display

    settings = Settings(profile_name)
    settings.validate()

    from majestic.storage import get_backend
    backend = get_backend(settings)

    session_id = "main"

    # Persistent working memory when enabled in persona.yaml
    working_memory = backend.working(session_id=session_id)

    channel = CLIChannel(session_id=session_id)
    llm_router = LLMRouter(settings)

    from majestic.memory.procedural import ProceduralMemory

    # Memory systems wired into gateway for per-request RAG
    _semantic = backend.semantic()
    _episodic = backend.episodic()
    _user_profile = backend.user_profile()

    startup = StartupManager(settings)
    incomplete = await startup.run()

    if incomplete:
        display.warn(f"{len(incomplete)} incomplete task(s) found — will resume on next run.")

    display.print_startup(profile_name, "foreground")

    # Register profile skills as slash-command completions
    _pm = None
    try:
        _shared = str(settings.shared_skills_dir)
        _pm = ProceduralMemory(str(settings.skills_dir), shared_dir=_shared)
        channel.set_skill_completions([s.get("name", "") for s in _pm.get_all()])
    except Exception:
        pass

    gateway = Gateway(settings, working_memory, channel,
                      episodic_memory=_episodic,
                      semantic_memory=_semantic,
                      user_profile=_user_profile)

    def _stream_cb(token: str) -> None:
        sys.stdout.write(token)
        sys.stdout.flush()

    _stream_callback = _stream_cb if settings.streaming else None
    runtime = _build_runtime(
        settings, working_memory, llm_router,
        stream_callback=_stream_callback,
        semantic=_semantic,
        user_profile=_user_profile,
        procedural_memory=_pm,
    )
    runtime = _register_tools(runtime, settings, semantic=_semantic)

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
            slash_result = await _handle_slash_plain(
                text, profile_name, working_memory, runtime, settings,
                semantic=_semantic, channel=channel, gateway=gateway,
            )
            if slash_result is True:
                continue
            elif isinstance(slash_result, str):
                text = slash_result  # skill expanded to task

        # Show previous task stats right below the user's input line
        if _last_stats:
            display.inline_stats(**_last_stats)

        working_memory.add_message("user", text)
        print()

        # Per-request enriched system prompt: persona + episodic history + semantic RAG
        system_prompt = gateway._build_enriched_system_prompt(text)

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


async def _handle_slash_plain(text: str, profile_name: str, working_memory, runtime, settings=None, semantic=None, channel=None, gateway=None):
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

    # Storage backend (pluggable) — handlers get stores via backend.pains() etc.
    backend = None
    if settings is not None:
        from majestic.storage import get_backend
        backend = get_backend(settings)

    cmd = text.strip().lower().split()[0]

    # Registry-first dispatch — migrated commands live in cli/commands/.
    # Unknown commands return None → fall through to legacy handlers below.
    from majestic.cli.commands import CommandContext, dispatch
    _ctx = CommandContext(
        text=text, profile_name=profile_name, working_memory=working_memory,
        runtime=runtime, settings=settings, semantic=semantic,
        channel=channel, gateway=gateway, backend=backend, console=console,
    )
    _res = await dispatch(_ctx)
    if _res is not None:
        return _res

    # Skill invocation: /skill_name [optional user input]
    if settings is not None:
        try:
            from majestic.memory.procedural import ProceduralMemory
            _shared_dir = str(settings.shared_skills_dir)
            pm = ProceduralMemory(str(settings.skills_dir), shared_dir=_shared_dir)
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
                    expanded = pm.expand_steps(steps)
                    lines.extend(f"  - {s}" for s in expanded)
                if user_input:
                    lines.append(f"\nUser input: {user_input}")
                print()
                out(f"  [dim]Running skill:[/dim] [bold]{cmd_name}[/bold]")
                return "\n".join(lines)
        except Exception:
            pass

    return False


def _build_runtime(
    settings,
    working_memory,
    llm_router,
    stream_callback=None,
    semantic=None,
    user_profile=None,
    procedural_memory=None,
) -> "AgentRuntime":
    """Instantiate AgentRuntime with the full self-evolution stack wired up."""
    from majestic.core.runtime import AgentRuntime
    from majestic.core.context_manager import ContextManager
    from majestic.core.skill_writer import SkillWriter
    from majestic.core.self_evolution import SelfEvolution
    from majestic.core.reflection import ReflectionEngine
    from majestic.core.planner import Planner
    from majestic.storage import get_backend

    data_dir   = settings.data_dir
    skills_dir = settings.skills_dir
    workspace  = settings.workspace_dir

    backend = get_backend(settings)
    lessons_store   = backend.lessons()
    episodic_memory = backend.episodic()
    checkpoint_store = backend.checkpoints()
    script_tracker  = backend.script_tracker()

    skill_writer = SkillWriter(llm_router, str(skills_dir))
    evolution    = SelfEvolution(
        llm_router=llm_router,
        skill_writer=skill_writer,
        script_tracker=script_tracker,
        lessons_store=lessons_store,
        workspace_dir=str(workspace),
        procedural_memory=procedural_memory,
    )

    consolidator = None
    if semantic is not None and user_profile is not None:
        from majestic.memory.consolidator import MemoryConsolidator
        consolidator = MemoryConsolidator(
            episodic=episodic_memory,
            semantic=semantic,
            user_profile=user_profile,
            llm_router=llm_router,
        )

    reflection_engine = ReflectionEngine(
        llm_router=llm_router,
        lessons_store=lessons_store,
        episodic_memory=episodic_memory,
        self_evolution=evolution,
        consolidator=consolidator,
    )
    planner = Planner(settings, llm_router, lessons_store)
    context_manager = ContextManager(llm_router=llm_router)

    return AgentRuntime(
        settings=settings,
        working_memory=working_memory,
        llm_router=llm_router,
        checkpoint_store=checkpoint_store,
        reflection_engine=reflection_engine,
        planner=planner,
        context_manager=context_manager,
        hitl_enabled=False,
        stream_callback=stream_callback,
    )


def _register_tools(runtime, settings, semantic=None):
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
        results = await web_search_fn(query, max_results, brave_api_key=brave_key)
        # Index results into semantic memory for future RAG retrieval
        if semantic is not None and isinstance(results, list):
            for r in results:
                try:
                    chunk = " ".join(filter(None, [
                        r.get("title", ""), r.get("snippet", ""), r.get("description", ""),
                    ]))
                    if chunk:
                        semantic.index(source=r.get("url", query), content=chunk)
                except Exception:
                    pass
        return results

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
