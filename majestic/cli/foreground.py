import asyncio


def run(profile_name: str = "default"):
    """Run agent in foreground interactive mode."""
    asyncio.run(_run_async(profile_name))


async def _run_async(profile_name: str):
    from majestic.config.settings import Settings
    from majestic.memory.working import WorkingMemory
    from majestic.core.gateway import Gateway
    from majestic.channels.cli import CLIChannel
    from majestic.core.runtime import AgentRuntime
    from majestic.llm.router import LLMRouter
    from majestic.system.startup import StartupManager
    import uuid

    print(f"\nLoading profile '{profile_name}'...", end="", flush=True)

    # Let FileNotFoundError / ValueError propagate to __main__ for clean output
    settings = Settings(profile_name)
    settings.validate()

    session_id = str(uuid.uuid4())[:8]
    working_memory = WorkingMemory()
    channel = CLIChannel(session_id=session_id)
    llm_router = LLMRouter(settings)

    startup = StartupManager(settings)
    await startup.run()

    gateway = Gateway(settings, working_memory, channel)
    system_prompt = gateway.build_system_prompt()

    runtime = AgentRuntime(settings, working_memory, llm_router)
    runtime = _register_tools(runtime, settings)

    name = settings.agent_name
    print(f"\r✓ Agent '{name}' ready. Type your message. Ctrl+C to exit.\n")
    print("─" * 50)

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
            print("Goodbye!")
            break

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
        "delegate_to_agent": agent_client.delegate,
    }

    return runtime
