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
    """Thin wrapper around the shared registry (Phase K.1) so foreground and
    background agents expose the identical toolset."""
    from majestic.tools.registry import register_tools
    return register_tools(runtime, settings, semantic=semantic)
