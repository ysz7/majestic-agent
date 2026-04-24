"""
Telegram gateway — replaces bot.py with the new Platform abstraction.

Free-text messages run through AgentLoop (tool calling).
Slash commands delegate to core/ functions directly.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Optional

from .base import Platform

logger = logging.getLogger(__name__)

TG_MAX = 4096
_SESSION_MAX = 10

# Per-user in-memory history and DB session IDs
_history:     dict[int, list[tuple[str, str]]] = {}
_db_sessions: dict[int, str] = {}

# Module-level app reference (used by _sync_notify)
_app = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _split_text(text: str, max_len: int = TG_MAX) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text); break
        cut = text.rfind("\n\n", 0, max_len)
        if cut < max_len // 3:
            cut = text.rfind("\n", 0, max_len)
        if cut < 0:
            cut = max_len
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return chunks


async def _send(update, msg, text: str, footer: str = "") -> None:
    from telegram.constants import ParseMode
    chunks = _split_text(text)
    for i, chunk in enumerate(chunks):
        payload = chunk + (footer if i == len(chunks) - 1 else "")
        if i == 0:
            await msg.edit_text(payload, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(payload, parse_mode=ParseMode.HTML)


def _fmt_sources(sources: list, mod: str = "all") -> str:
    if not sources:
        return ""
    doc_s   = [s for s in sources if not s.startswith("intel:")]
    intel_s = [s for s in sources if s.startswith("intel:")]
    parts = []
    if doc_s:
        parts.append(f"📄 <i>{', '.join(doc_s)}</i>")
    if intel_s and mod in ("all", "intel"):
        parts.append(f"🔍 <i>{', '.join(s.replace('intel:','') for s in intel_s)}</i>")
    return "\n" + " │ ".join(parts) if parts else ""


def _sync_notify(text: str) -> None:
    """Thread-safe push notification (used by reminders, autonomous agent)."""
    global _app
    from majestic.config import get as cfg_get
    allowed = cfg_get("telegram.allowed_user_ids") or []
    if not _app or not allowed:
        print(f"[notify] {text}")
        return
    from core.formatter import render_telegram
    from telegram.constants import ParseMode
    chunks = _split_text(render_telegram(text))
    loop = asyncio.get_event_loop()
    for uid in allowed:
        for chunk in chunks:
            try:
                coro = _app.bot.send_message(chat_id=uid, text=chunk, parse_mode=ParseMode.HTML)
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(coro, loop)
                else:
                    loop.run_until_complete(coro)
            except Exception as e:
                logger.error(f"notify → {uid}: {e}")


def _get_session(uid: int, model_label: str = "") -> str:
    """Return existing or create new StateDB session for this user."""
    if uid not in _db_sessions:
        try:
            from majestic.db.state import StateDB
            sid = StateDB().create_session(source="telegram", model=model_label)
            _db_sessions[uid] = sid
        except Exception:
            _db_sessions[uid] = ""
    return _db_sessions[uid]


# ── Concurrency gate (one per heavy command) ──────────────────────────────────

class _Gate:
    def __init__(self):
        self._lock   = asyncio.Lock()
        self._busy   = False
        self._done   = asyncio.Event()
        self._done.set()
        self._result = None
        self._error: Optional[Exception] = None

    async def run(self, fn, *args):
        async with self._lock:
            if not self._busy:
                self._busy = True; self._error = None; self._done.clear()
                am_runner = True
            else:
                am_runner = False
        if am_runner:
            try:
                self._result = await asyncio.to_thread(fn, *args)
            except Exception as e:
                self._error = e; self._result = None
            finally:
                async with self._lock: self._busy = False
                self._done.set()
            if self._error: raise self._error
            return self._result, True
        else:
            await self._done.wait()
            if self._error: raise self._error
            return self._result, False


_gates = {k: _Gate() for k in ("research", "briefing", "ideas", "market", "predictions", "flows")}


# ── Access control ────────────────────────────────────────────────────────────

def _allowed(update) -> bool:
    from majestic.config import get as cfg_get
    allowed = cfg_get("telegram.allowed_user_ids") or []
    if not allowed:
        return True
    return update.effective_user and update.effective_user.id in set(allowed)


async def _deny(update) -> None:
    await update.message.reply_text("⛔ Access denied.")


# ── Handlers ──────────────────────────────────────────────────────────────────

async def handle_start(update, context):
    if not _allowed(update): return await _deny(update)
    from majestic.config import get as cfg_get
    from telegram.constants import ParseMode
    await update.message.reply_text(
        "👋 <b>Majestic</b>\n\nUniversal AI agent. Just send me a message or use a command.\n\n"
        "<b>Commands:</b> /research /briefing /ideas /market /news /ask /report /stats /tokens /skills",
        parse_mode=ParseMode.HTML,
    )


async def handle_text(update, context):
    """Free-text → AgentLoop (tool calling)."""
    if not _allowed(update): return await _deny(update)
    question = (update.message.text or "").strip()
    if not question: return
    uid     = update.effective_user.id
    history = _history.get(uid, [])
    msg     = await update.message.reply_text("⏳ Thinking...")

    try:
        from majestic.agent.loop import AgentLoop
        from core.formatter import render_telegram
        from telegram.constants import ParseMode

        session_id = _get_session(uid)
        loop = AgentLoop()
        result = await asyncio.to_thread(
            loop.run, question, session_id, history,
        )
        answer = render_telegram(result["answer"])
        footer = _fmt_sources(result.get("sources", []))
        await _send(update, msg, answer, footer=footer)

        hist = _history.setdefault(uid, [])
        hist.append((question, result["answer"]))
        if len(hist) > _SESSION_MAX:
            _history[uid] = hist[-_SESSION_MAX:]

    except Exception as e:
        logger.exception("handle_text")
        await msg.edit_text(f"❌ Error: {e}")


async def handle_ask(update, context):
    if not _allowed(update): return await _deny(update)
    question = " ".join(context.args or []).strip()
    if not question:
        await update.message.reply_text("Usage: /ask <question>"); return
    uid  = update.effective_user.id
    msg  = await update.message.reply_text("⏳ Searching...")
    try:
        from core.rag_engine import ask
        from core.config import get_mod
        from core.formatter import render_telegram
        result = await asyncio.to_thread(ask, question, None, _history.get(uid, []), get_mod())
        answer = render_telegram(result["answer"])
        footer = _fmt_sources(result.get("sources", []), get_mod())
        await _send(update, msg, answer, footer=footer)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")


async def handle_research(update, context):
    if not _allowed(update): return await _deny(update)
    msg = await update.message.reply_text("🔍 Collecting intel…")
    try:
        from core.intel import collect_and_index
        result, fresh = await _gates["research"].run(collect_and_index)
        total = result.get("total_new", 0)
        label = "fresh" if fresh else "shared"
        await msg.edit_text(f"✅ Done ({label}). New items: {total}")
    except Exception as e:
        await msg.edit_text(f"❌ {e}")


async def handle_briefing(update, context):
    if not _allowed(update): return await _deny(update)
    try: days = int(context.args[0]) if context.args else 14
    except ValueError: days = 14
    msg = await update.message.reply_text(f"📰 Generating {days}d briefing…")
    try:
        from core.trends import generate_briefing
        from core.formatter import render_telegram
        result, fresh = await _gates["briefing"].run(generate_briefing, days)
        await _send(update, msg, render_telegram(result))
    except Exception as e:
        await msg.edit_text(f"❌ {e}")


async def handle_predict(update, context):
    if not _allowed(update): return await _deny(update)
    try: days = int(context.args[0]) if context.args else 14
    except ValueError: days = 14
    msg = await update.message.reply_text(f"🔮 Generating predictions ({days}d)…")
    try:
        from core.trends import generate_predictions
        from core.formatter import render_telegram
        result, _ = await _gates["predictions"].run(generate_predictions, days)
        await _send(update, msg, render_telegram(result))
    except Exception as e:
        await msg.edit_text(f"❌ {e}")


async def handle_flows(update, context):
    if not _allowed(update): return await _deny(update)
    try: days = int(context.args[0]) if context.args else 14
    except ValueError: days = 14
    msg = await update.message.reply_text(f"💸 Analyzing money flows ({days}d)…")
    try:
        from core.trends import generate_money_flows
        from core.formatter import render_telegram
        result, _ = await _gates["flows"].run(generate_money_flows, days)
        await _send(update, msg, render_telegram(result))
    except Exception as e:
        await msg.edit_text(f"❌ {e}")


async def handle_ideas(update, context):
    if not _allowed(update): return await _deny(update)
    msg = await update.message.reply_text("💡 Generating ideas…")
    try:
        from core.agent import generate_ideas
        from core.formatter import render_telegram
        result, _ = await _gates["ideas"].run(generate_ideas)
        await _send(update, msg, render_telegram(result))
    except Exception as e:
        await msg.edit_text(f"❌ {e}")


async def handle_market(update, context):
    if not _allowed(update): return await _deny(update)
    msg = await update.message.reply_text("📈 Fetching market data…")
    try:
        from core.market_pulse import get_snapshot
        from core.formatter import render_telegram
        result, _ = await _gates["market"].run(get_snapshot)
        await _send(update, msg, render_telegram(str(result)))
    except Exception as e:
        await msg.edit_text(f"❌ {e}")


async def handle_news(update, context):
    if not _allowed(update): return await _deny(update)
    try: limit = int(context.args[0]) if context.args else 10
    except ValueError: limit = 10
    msg = await update.message.reply_text("📡 Loading news…")
    try:
        from majestic.db.state import StateDB
        from core.formatter import render_telegram
        rows = StateDB().search_news("*", k=limit)
        if not rows:
            await msg.edit_text("No news found. Run /research first."); return
        lines = [f"<b>{i+1}.</b> [{r['source']}] {r['title']}" for i, r in enumerate(rows)]
        await _send(update, msg, "\n".join(lines))
    except Exception as e:
        await msg.edit_text(f"❌ {e}")


async def handle_stats(update, context):
    if not _allowed(update): return await _deny(update)
    try:
        from core.rag_engine import stats
        s = stats()
        await update.message.reply_text(
            f"📊 <b>Knowledge base</b>\nChunks: {s['chunks']}\nFiles: {s['files']}",
            parse_mode="HTML",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")


async def handle_skills(update, context):
    if not _allowed(update): return await _deny(update)
    try:
        from majestic.skills.store import list_skills
        skills = list_skills()
        if not skills:
            await update.message.reply_text("No skills saved yet. They are created automatically after complex tasks.")
            return
        lines = [f"/{s['name']} — {s.get('description','')}" for s in skills]
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")


async def handle_memory(update, context):
    if not _allowed(update): return await _deny(update)
    try:
        from majestic.memory.store import show
        from core.formatter import render_telegram
        await update.message.reply_text(render_telegram(show()), parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")


async def handle_tokens(update, context):
    if not _allowed(update): return await _deny(update)
    from core.token_tracker import format_stats
    await update.message.reply_text(f"<pre>{format_stats()}</pre>", parse_mode="HTML")


async def handle_set(update, context):
    if not _allowed(update): return await _deny(update)
    args = context.args or []
    if len(args) >= 2:
        key, val = args[0].lower(), args[1].upper()
        from core.config import set_lang, set_currency, set_mod
        if key == "lang":     set_lang(val);     await update.message.reply_text(f"✅ Language → {val}")
        elif key == "currency": set_currency(val); await update.message.reply_text(f"✅ Currency → {val}")
        elif key == "mod":    set_mod(val.lower()); await update.message.reply_text(f"✅ Scope → {val.lower()}")
        else: await update.message.reply_text("Usage: /set lang|currency|mod <value>")
    else:
        from core.config import get_lang, get_currency, get_mod
        await update.message.reply_text(
            f"lang={get_lang()}  currency={get_currency()}  mod={get_mod()}"
        )


async def handle_logs(update, context):
    if not _allowed(update): return await _deny(update)
    try:
        from core.error_logger import get_recent
        lines = get_recent(10)
        text = "\n".join(lines) if lines else "No errors logged."
        await update.message.reply_text(f"<pre>{text[:3000]}</pre>", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")


async def handle_report(update, context):
    if not _allowed(update): return await _deny(update)
    topic = " ".join(context.args or []).strip()
    if not topic:
        await update.message.reply_text("Usage: /report <topic>"); return
    msg = await update.message.reply_text(f"📝 Generating report: {topic[:60]}…")
    try:
        from core.rag_engine import ask
        from core.formatter import render_telegram
        result = await asyncio.to_thread(ask, f"Create detailed report on: {topic}", scope="all")
        await _send(update, msg, render_telegram(result["answer"]))
    except Exception as e:
        await msg.edit_text(f"❌ {e}")


async def handle_remind(update, context):
    if not _allowed(update): return await _deny(update)
    text = " ".join(context.args or []).strip()
    if not text:
        await update.message.reply_text("Usage: /remind <text with date>"); return
    try:
        from core.reminders import extract_reminder_intent, add_reminder, format_reminder
        intent = extract_reminder_intent(text)
        if not intent:
            await update.message.reply_text("❌ Could not parse date/time."); return
        r = add_reminder(intent["title"], intent["dt"])
        await update.message.reply_text(f"✅ {format_reminder(r)}")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")


async def handle_reminders(update, context):
    if not _allowed(update): return await _deny(update)
    from core.reminders import list_reminders, format_reminder
    items = list_reminders()
    if not items:
        await update.message.reply_text("No active reminders."); return
    lines = [f"{i+1}. {format_reminder(r)}" for i, r in enumerate(items)]
    await update.message.reply_text("\n".join(lines))


async def handle_document(update, context):
    if not _allowed(update): return await _deny(update)
    doc = update.message.document
    if not doc: return
    suffix = Path(doc.file_name or "").suffix.lower()
    if suffix not in {".pdf", ".docx", ".csv", ".txt", ".md"}:
        await update.message.reply_text(f"❌ Unsupported format: {suffix}"); return
    msg = await update.message.reply_text(f"📥 Downloading {doc.file_name}…")
    try:
        from majestic.constants import WORKSPACE_DIR
        inbox = WORKSPACE_DIR / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        dest = inbox / doc.file_name
        tg_file = await context.bot.get_file(doc.file_id)
        await tg_file.download_to_drive(str(dest))
        await msg.edit_text(f"⏳ Indexing {doc.file_name}…")
        from core.rag_engine import index_file
        n = await asyncio.to_thread(index_file, dest)
        await msg.edit_text(f"✅ Indexed {doc.file_name} — {n} chunks")
    except Exception as e:
        await msg.edit_text(f"❌ {e}")


# ── Background services ───────────────────────────────────────────────────────

def _start_services() -> None:
    from core.backup import start_backup_scheduler
    from core.reminders import start_watcher
    from core.agent import start_autonomous_agent, set_notify
    from core.intel import collect_and_index

    start_backup_scheduler()
    start_watcher(on_due=lambda r: _sync_notify(f"⏰ Reminder: {r['title']}"))
    set_notify(_sync_notify)
    start_autonomous_agent(collect_fn=collect_and_index)


# ── Platform class ────────────────────────────────────────────────────────────

class TelegramPlatform(Platform):
    @property
    def name(self) -> str:
        return "telegram"

    def is_configured(self) -> bool:
        from majestic.config import load_env
        load_env()
        return bool(os.getenv("TELEGRAM_BOT_TOKEN"))

    async def start(self) -> None:
        global _app
        from telegram import BotCommand
        from telegram.ext import (
            Application, CommandHandler, MessageHandler, filters,
        )
        from majestic.config import load_env, sync_env_from_config
        from majestic.memory.store import load_both
        from core.rag_engine import set_memory_context

        sync_env_from_config()
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not token:
            logger.error("TELEGRAM_BOT_TOKEN not set"); return

        # Load persistent memory
        try:
            mem = load_both()
            if mem:
                set_memory_context(mem)
        except Exception:
            pass

        async def _post_init(app: Application):
            await app.bot.set_my_commands([
                BotCommand("start",      "Show welcome"),
                BotCommand("research",   "Collect intel from all sources"),
                BotCommand("briefing",   "World briefing (/briefing 14)"),
                BotCommand("predict",    "Predictions (/predict 14)"),
                BotCommand("flows",      "Money flows (/flows 14)"),
                BotCommand("ideas",      "5 business ideas"),
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
            ])

        app = (
            Application.builder()
            .token(token)
            .post_init(_post_init)
            .build()
        )
        _app = app

        app.add_handler(CommandHandler("start",      handle_start))
        app.add_handler(CommandHandler("research",   handle_research))
        app.add_handler(CommandHandler("briefing",   handle_briefing))
        app.add_handler(CommandHandler("predict",    handle_predict))
        app.add_handler(CommandHandler("flows",      handle_flows))
        app.add_handler(CommandHandler("ideas",      handle_ideas))
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
        app.add_handler(MessageHandler(filters.Document.ALL,           handle_document))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

        _start_services()
        logger.info("Telegram bot started.")
        await app.run_polling(drop_pending_updates=True)

    async def stop(self) -> None:
        global _app
        if _app:
            await _app.stop()
            _app = None
