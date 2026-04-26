"""
Telegram gateway — Platform implementation.

State and helpers: state.py
Handlers:          handlers.py
"""
from __future__ import annotations

import logging
import os

from ..base import Platform

logger = logging.getLogger(__name__)


def _start_services(notify_fn) -> None:
    from majestic.backup import start_backup_scheduler
    from majestic.reminders import start_watcher
    from majestic.agent.runner import start_autonomous_agent, set_notify
    from majestic.tools.research.collect import collect_and_index
    from majestic.cron.scheduler import start_scheduler

    start_backup_scheduler()
    start_watcher(on_due=lambda r: notify_fn(f"⏰ Reminder: {r['text']}"))
    set_notify(notify_fn)
    start_autonomous_agent(collect_fn=collect_and_index)
    start_scheduler(delivery={"telegram": notify_fn, "cli": print})


class TelegramPlatform(Platform):
    @property
    def name(self) -> str:
        return "telegram"

    def is_configured(self) -> bool:
        from majestic.config import load_env
        load_env()
        return bool(os.getenv("TELEGRAM_BOT_TOKEN"))

    async def start(self) -> None:
        from telegram import BotCommand
        from telegram.ext import Application, CommandHandler, MessageHandler, filters
        from majestic.config import sync_env_from_config
        from majestic.memory.store import load_both
        from .state import _sync_notify
        from . import state as _st
        from .handlers import (
            handle_start, handle_text, handle_ask,
            handle_research, handle_briefing, handle_market,
            handle_news, handle_report, handle_skills, handle_memory,
            handle_tokens, handle_stats, handle_set, handle_logs,
            handle_remind, handle_reminders, handle_schedule, handle_document,
        )

        sync_env_from_config()
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not token:
            logger.error("TELEGRAM_BOT_TOKEN not set"); return

        try:
            load_both()
        except Exception:
            pass

        async def _post_init(app: Application):
            await app.bot.set_my_commands([
                BotCommand("start",      "Show welcome"),
                BotCommand("research",   "Collect intel from all sources"),
                BotCommand("briefing",   "World briefing (/briefing 14)"),
                BotCommand("market",     "Market snapshot"),
                BotCommand("news",       "Latest news (/news 20)"),
                BotCommand("ask",        "Search knowledge base"),
                BotCommand("report",     "Generate report on a topic"),
                BotCommand("skills",     "List saved skills"),
                BotCommand("memory",     "View persistent memory"),
                BotCommand("tokens",     "Token usage and cost"),
                BotCommand("stats",      "Knowledge base stats"),
                BotCommand("set",        "Settings (/set lang EN)"),
                BotCommand("logs",       "Recent error log"),
                BotCommand("remind",     "Add reminder"),
                BotCommand("reminders",  "List reminders"),
                BotCommand("schedule",   "Cron schedules: add/list/remove"),
            ])

        app = Application.builder().token(token).post_init(_post_init).build()
        _st._app = app

        app.add_handler(CommandHandler("start",      handle_start))
        app.add_handler(CommandHandler("research",   handle_research))
        app.add_handler(CommandHandler("briefing",   handle_briefing))
        app.add_handler(CommandHandler("market",     handle_market))
        app.add_handler(CommandHandler("news",       handle_news))
        app.add_handler(CommandHandler("ask",        handle_ask))
        app.add_handler(CommandHandler("report",     handle_report))
        app.add_handler(CommandHandler("skills",     handle_skills))
        app.add_handler(CommandHandler("memory",     handle_memory))
        app.add_handler(CommandHandler("tokens",     handle_tokens))
        app.add_handler(CommandHandler("stats",      handle_stats))
        app.add_handler(CommandHandler("set",        handle_set))
        app.add_handler(CommandHandler("logs",       handle_logs))
        app.add_handler(CommandHandler("remind",     handle_remind))
        app.add_handler(CommandHandler("reminders",  handle_reminders))
        app.add_handler(CommandHandler("schedule",   handle_schedule))
        app.add_handler(MessageHandler(filters.Document.ALL,            handle_document))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

        _start_services(notify_fn=_sync_notify)
        logger.info("Telegram bot started.")
        await app.run_polling(drop_pending_updates=True)

    async def stop(self) -> None:
        from . import state as _st
        if _st._app:
            await _st._app.stop()
            _st._app = None
