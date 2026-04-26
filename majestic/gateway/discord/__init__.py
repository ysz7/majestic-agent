"""
Discord gateway — Platform implementation using discord.py.

Slash commands: /ask, /briefing, /research, /news, /market, /remind, /schedule
Free text in DMs or @mentions → agent query.
"""
from __future__ import annotations

import logging
import os

from ..base import Platform

logger = logging.getLogger(__name__)

_CHUNK = 1900  # Discord message limit safety margin


class DiscordPlatform(Platform):
    @property
    def name(self) -> str:
        return "discord"

    def is_configured(self) -> bool:
        from majestic import config as _cfg
        _cfg.load_env()
        return bool(os.getenv("DISCORD_BOT_TOKEN"))

    async def start(self) -> None:
        try:
            import discord
            from discord import app_commands
        except ImportError:
            logger.error("discord.py not installed — run: pip install discord.py")
            return

        token = os.getenv("DISCORD_BOT_TOKEN", "")
        if not token:
            logger.error("DISCORD_BOT_TOKEN not set"); return

        intents = discord.Intents.default()
        intents.message_content = True
        client  = discord.Client(intents=intents)
        tree    = app_commands.CommandTree(client)

        # ── helpers ──────────────────────────────────────────────────────────

        async def _reply(interaction: discord.Interaction, text: str) -> None:
            from ..formatter import render_discord, chunk_discord
            rendered = render_discord(text)
            chunks   = chunk_discord(rendered)
            await interaction.response.send_message(chunks[0])
            for chunk in chunks[1:]:
                await interaction.followup.send(chunk)

        async def _run_agent(prompt: str) -> str:
            import asyncio
            from majestic.agent.loop import AgentLoop
            loop = AgentLoop()
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: loop.run(prompt, session_id=None, history=[])
            )
            return result.get("answer", "(no answer)")

        async def _run_cmd(cmd: str, args: dict) -> str:
            import asyncio
            from majestic.cli.commands import dispatch
            return await asyncio.get_event_loop().run_in_executor(
                None, lambda: dispatch(cmd, args)
            )

        # ── slash commands ────────────────────────────────────────────────────

        @tree.command(name="ask", description="Ask the agent anything")
        @app_commands.describe(query="Your question or task")
        async def cmd_ask(interaction: discord.Interaction, query: str):
            await interaction.response.defer()
            answer = await _run_agent(query)
            from ..formatter import render_discord, chunk_discord
            chunks = chunk_discord(render_discord(answer))
            await interaction.followup.send(chunks[0])
            for chunk in chunks[1:]:
                await interaction.followup.send(chunk)

        @tree.command(name="briefing", description="Market and tech briefing")
        @app_commands.describe(days="Number of days to cover (default 14)")
        async def cmd_briefing(interaction: discord.Interaction, days: int = 14):
            await interaction.response.defer()
            text = await _run_cmd("briefing", {"days": days})
            from ..formatter import render_discord, chunk_discord
            chunks = chunk_discord(render_discord(text))
            await interaction.followup.send(chunks[0])
            for chunk in chunks[1:]:
                await interaction.followup.send(chunk)

        @tree.command(name="research", description="Collect fresh intel from all sources")
        async def cmd_research(interaction: discord.Interaction):
            await interaction.response.defer()
            text = await _run_cmd("research", {})
            from ..formatter import render_discord, chunk_discord
            chunks = chunk_discord(render_discord(text))
            await interaction.followup.send(chunks[0])
            for chunk in chunks[1:]:
                await interaction.followup.send(chunk)

        @tree.command(name="news", description="Latest news")
        @app_commands.describe(limit="Number of items (default 10)")
        async def cmd_news(interaction: discord.Interaction, limit: int = 10):
            await interaction.response.defer()
            text = await _run_cmd("news", {"limit": limit})
            from ..formatter import render_discord, chunk_discord
            chunks = chunk_discord(render_discord(text))
            await interaction.followup.send(chunks[0])
            for chunk in chunks[1:]:
                await interaction.followup.send(chunk)

        @tree.command(name="market", description="Crypto, stocks, and forex snapshot")
        async def cmd_market(interaction: discord.Interaction):
            await interaction.response.defer()
            text = await _run_cmd("market", {})
            from ..formatter import render_discord, chunk_discord
            chunks = chunk_discord(render_discord(text))
            await interaction.followup.send(chunks[0])
            for chunk in chunks[1:]:
                await interaction.followup.send(chunk)

        @tree.command(name="remind", description="Set a natural language reminder")
        @app_commands.describe(text="What to remind you about (e.g. 'in 2 hours check the build')")
        async def cmd_remind(interaction: discord.Interaction, text: str):
            try:
                from majestic.reminders import add_reminder
                add_reminder(text)
                await interaction.response.send_message(f"✓ Reminder set: {text}")
            except Exception as e:
                await interaction.response.send_message(f"Error: {e}")

        @tree.command(name="schedule", description="Add a recurring schedule")
        @app_commands.describe(text="e.g. 'every Monday at 9am send me a briefing'")
        async def cmd_schedule(interaction: discord.Interaction, text: str):
            try:
                from majestic.cron.jobs import nl_to_schedule, add_schedule
                sched = nl_to_schedule(text)
                add_schedule(
                    name=sched["name"],
                    cron_expr=sched["cron"],
                    prompt=sched["prompt"],
                    delivery_target=sched.get("target", "discord"),
                )
                await interaction.response.send_message(
                    f"✓ Schedule added: **{sched['name']}** (`{sched['cron']}`)"
                )
            except Exception as e:
                await interaction.response.send_message(f"Error: {e}")

        # ── message handler (DMs + mentions) ──────────────────────────────────

        @client.event
        async def on_message(message: discord.Message):
            if message.author == client.user:
                return
            is_dm      = isinstance(message.channel, discord.DMChannel)
            is_mention = client.user in message.mentions
            if not (is_dm or is_mention):
                return
            text = message.content
            if is_mention:
                text = text.replace(f"<@{client.user.id}>", "").strip()
            if not text:
                return
            async with message.channel.typing():
                answer = await _run_agent(text)
            from ..formatter import render_discord, chunk_discord
            chunks = chunk_discord(render_discord(answer))
            for chunk in chunks:
                await message.channel.send(chunk)

        @client.event
        async def on_ready():
            await tree.sync()
            logger.info(f"Discord bot ready as {client.user}")
            print(f"  Discord bot online: {client.user}")

        async def stop(self) -> None:
            await client.close()

        DiscordPlatform.stop = stop

        logger.info("Starting Discord bot...")
        await client.start(token)

    async def stop(self) -> None:
        pass  # overwritten after client is created in start()
