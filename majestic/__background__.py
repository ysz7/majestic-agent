"""
majestic.__background__
~~~~~~~~~~~~~~~~~~~~~~~~
Entry point for background (HTTP server) agent mode.

Invoked by ``majestic run <profile>`` as a detached subprocess::

    python -m majestic.__background__ <profile_name>

Runs the FastAPI HTTP server and the agent's ReAct loop concurrently via
``asyncio.gather``.  Tasks arrive through the ServerChannel queue; results
are stored back in the channel after each turn.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger("majestic.background")


async def run_agent_loop(settings, channel) -> None:
    from majestic.core.runtime import AgentRuntime
    from majestic.memory.working import WorkingMemory
    from majestic.llm.router import LLMRouter
    from majestic.core.api.ws import emit_event
    from majestic.tools.registry import register_tools

    llm = LLMRouter(settings)
    memory = WorkingMemory()

    # Bridge streaming tokens from the runtime to all connected WebSocket clients
    # so the desktop chat panel can render incremental output live.
    def _stream_callback(token: str) -> None:
        emit_event({"type": "token", "content": token})

    runtime = AgentRuntime(
        settings, memory, llm_router=llm, stream_callback=_stream_callback
    )

    # Phase K.1 — give the background/desktop agent the SAME toolset as the CLI
    # (previously it ran with no tools: pure LLM reasoning only). Semantic memory
    # is optional and best-effort, used to index web_search results for RAG.
    semantic = None
    try:
        from majestic.storage import get_backend
        semantic = get_backend(settings).semantic()
    except Exception:
        pass
    try:
        register_tools(runtime, settings, semantic=semantic)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tool registration failed — agent will run without tools: %s", exc)

    # Phase K.3 — connect enabled MCP servers and merge their tools into the loop.
    mcp_manager = None
    try:
        from majestic.mcp.client import MCPManager
        from pathlib import Path as _Path

        registry = _Path(__file__).resolve().parent / "mcp" / "registry.yaml"
        mcp_manager = MCPManager(registry)
        mcp_tools = await mcp_manager.connect_enabled()
        if mcp_tools:
            runtime.tools.update(mcp_tools)
            logger.info("MCP: %d tool(s) merged into the agent loop", len(mcp_tools))
    except Exception as exc:  # noqa: BLE001
        logger.warning("MCP connect failed (non-fatal): %s", exc)

    try:
        while True:
            task = await channel.receive()
            text = task.get("text", "")
            task_id = task.get("task_id", "")

            try:
                result = await runtime.run(text, task_id=task_id)
                emit_event(
                    {
                        "type": "done",
                        "task_id": task_id,
                        "result": result,
                        "tokens": getattr(runtime, "_tokens_used", 0),
                        "cost": getattr(runtime, "_cost_used", 0.0),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                result = f"Error: {exc}"
                emit_event({"type": "error", "message": str(exc), "task_id": task_id})

            await channel.send(result)
            if hasattr(channel, "store_result"):
                channel.store_result(task_id, result)
    finally:
        # Phase K.3 — tear down MCP server subprocesses on shutdown/cancel.
        if mcp_manager is not None:
            try:
                await mcp_manager.close_all()
            except Exception:
                pass


async def main(profile_name: str) -> None:
    """Bootstrap and run the background agent.

    Args:
        profile_name: Name of the profile directory under ``profiles/``.
    """
    from majestic.config.settings import Settings
    from majestic.channels.server_channel import ServerChannel
    from majestic.core.server import create_app, start_server

    settings = Settings(profile_name)
    channel = ServerChannel(session_id=profile_name)
    app = create_app(channel, settings)

    # Schedule cron-triggered workflows for this profile.
    from majestic.core.scheduler import WorkflowScheduler

    scheduler = WorkflowScheduler(channel)
    app.state.scheduler = scheduler

    loop = asyncio.get_running_loop()
    shutdown = asyncio.Event()

    def _request_shutdown():
        shutdown.set()

    try:
        loop.add_signal_handler(signal.SIGTERM, _request_shutdown)
        loop.add_signal_handler(signal.SIGINT, _request_shutdown)
    except NotImplementedError:
        # Windows — synchronous signal handler
        def _sync_handler(signum, frame):
            loop.call_soon_threadsafe(_request_shutdown)
        signal.signal(signal.SIGTERM, _sync_handler)
        signal.signal(signal.SIGINT, _sync_handler)

    server_task = asyncio.create_task(start_server(app, settings.agent_port))
    agent_task = asyncio.create_task(run_agent_loop(settings, channel))

    # Start cron scheduling now that the event loop is running.
    try:
        scheduler.start([profile_name])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Workflow scheduler failed to start: %s", exc)

    await shutdown.wait()

    logger.warning("Shutdown signal received — draining (up to 30 s)...")
    scheduler.shutdown()
    server_task.cancel()
    agent_task.cancel()
    try:
        await asyncio.wait_for(
            asyncio.gather(server_task, agent_task, return_exceptions=True),
            timeout=30.0,
        )
    except asyncio.TimeoutError:
        logger.warning("Drain timeout — forcing exit.")


if __name__ == "__main__":
    profile = sys.argv[1] if len(sys.argv) > 1 else "default"
    asyncio.run(main(profile))
