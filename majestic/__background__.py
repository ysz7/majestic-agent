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
import sys

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


async def run_agent_loop(settings, channel) -> None:
    """Continuously receive tasks from the channel and run the agent.

    A minimal LLM router is constructed from the available API keys found
    in the profile settings.  The loop runs indefinitely until cancelled.

    Args:
        settings: Loaded Settings object for the active profile.
        channel:  ServerChannel instance shared with the HTTP server.
    """
    from majestic.core.runtime import AgentRuntime
    from majestic.memory.working import WorkingMemory

    # Build a lightweight LLM router that wraps whichever provider is
    # configured for this profile.
    llm = _build_llm_router(settings)

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
        # Persist result so HTTP callers can retrieve it later.
        channel.store_result(task_id, result) if hasattr(channel, "store_result") else None


def _build_llm_router(settings):
    """Return the best available LLM provider for the given settings.

    Tries providers in order: Anthropic → OpenRouter → raises RuntimeError.

    Args:
        settings: Settings instance with API key properties.

    Returns:
        An LLM provider instance compatible with ``BaseLLM``.

    Raises:
        RuntimeError: If no API key is configured.
    """
    from majestic.llm.openrouter import OpenRouterLLM

    class _RoutingLLM:
        """Minimal router that picks a model string and delegates to a provider."""

        def __init__(self, provider, settings) -> None:
            self._provider = provider
            self._settings = settings

        async def chat(self, messages: list[dict], step_type: str = "reason", **kwargs) -> dict:
            model = self._settings.get_model(step_type)
            return await self._provider.chat(messages, model=model, **kwargs)

    if settings.anthropic_api_key:
        from majestic.llm.anthropic import AnthropicLLM
        provider = AnthropicLLM(api_key=settings.anthropic_api_key)
    elif settings.openrouter_api_key:
        provider = OpenRouterLLM(api_key=settings.openrouter_api_key)
    else:
        raise RuntimeError(
            f"Profile '{settings.profile_name}' has no LLM API key configured."
        )

    return _RoutingLLM(provider, settings)


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

    await asyncio.gather(
        start_server(app, settings.agent_port),
        run_agent_loop(settings, channel),
    )


if __name__ == "__main__":
    profile = sys.argv[1] if len(sys.argv) > 1 else "default"
    asyncio.run(main(profile))
