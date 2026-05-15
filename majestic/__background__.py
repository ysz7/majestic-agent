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


async def run_agent_loop(settings, channel) -> None:
    from majestic.core.runtime import AgentRuntime
    from majestic.memory.working import WorkingMemory
    from majestic.llm.router import LLMRouter

    llm = LLMRouter(settings)
    memory = WorkingMemory()
    runtime = AgentRuntime(settings, memory, llm_router=llm)

    while True:
        task = await channel.receive()
        text = task.get("text", "")
        task_id = task.get("task_id", "")

        try:
            result = await runtime.run(text, task_id=task_id)
        except Exception as exc:  # noqa: BLE001
            result = f"Error: {exc}"

        await channel.send(result)
        if hasattr(channel, "store_result"):
            channel.store_result(task_id, result)


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

    await shutdown.wait()

    logger.warning("Shutdown signal received — draining (up to 30 s)...")
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
