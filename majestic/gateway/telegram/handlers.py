"""
Telegram command and message handlers.

All handlers import shared state from state.py to avoid circular imports.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from .state import (
    _history, _db_sessions, _gates, _SESSION_MAX,
    _allowed, _deny, _send, _fmt_sources, _get_session,
)

logger = logging.getLogger(__name__)


async def handle_start(update, context):
    if not _allowed(update): return await _deny(update)
    await update.message.reply_text(
        "👋 <b>Majestic</b>\n\nUniversal AI agent. Just send me a message or use a command.\n\n"
        "<b>Commands:</b> /research /briefing /market /news /ask /report /skills /memory /tokens",
        parse_mode="HTML",
    )


async def handle_text(update, context):
    if not _allowed(update): return await _deny(update)
    question = (update.message.text or "").strip()
    if not question: return
    uid     = update.effective_user.id
    history = _history.get(uid, [])
    msg     = await update.message.reply_text("⏳ Thinking...")
    try:
        from majestic.agent.loop import AgentLoop
        from majestic.gateway.formatter import render_telegram
        session_id = _get_session(uid)
        result = await asyncio.to_thread(
            AgentLoop().run, question, session_id, history,
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
    uid = update.effective_user.id
    msg = await update.message.reply_text("⏳ Searching...")
    try:
        from majestic.rag import ask
        from majestic.config import get
        from majestic.gateway.formatter import render_telegram
        result = await asyncio.to_thread(ask, question, None, _history.get(uid, []), get("search_mode", "all"))
        await _send(update, msg, render_telegram(result["answer"]),
                    footer=_fmt_sources(result.get("sources", []), get("search_mode", "all")))
    except Exception as e:
        await msg.edit_text(f"❌ {e}")


async def handle_research(update, context):
    if not _allowed(update): return await _deny(update)
    msg = await update.message.reply_text("🔍 Collecting intel…")
    try:
        from majestic.tools.research.collect import collect_and_index
        result, fresh = await _gates["research"].run(collect_and_index)
        total = result.get("total_new", 0)
        await msg.edit_text(f"✅ Done ({'fresh' if fresh else 'shared'}). New items: {total}")
    except Exception as e:
        await msg.edit_text(f"❌ {e}")


async def handle_briefing(update, context):
    if not _allowed(update): return await _deny(update)
    try: days = int(context.args[0]) if context.args else 14
    except ValueError: days = 14
    msg = await update.message.reply_text(f"📰 Generating {days}d briefing…")
    try:
        from majestic.tools.research.briefing import generate_briefing
        from majestic.gateway.formatter import render_telegram
        result, _ = await _gates["briefing"].run(generate_briefing, days)
        await _send(update, msg, render_telegram(result))
    except Exception as e:
        await msg.edit_text(f"❌ {e}")


async def handle_market(update, context):
    if not _allowed(update): return await _deny(update)
    msg = await update.message.reply_text("📈 Fetching market data…")
    try:
        from majestic.tools.research.market_data import collect_market_pulse, format_pulse
        from majestic.gateway.formatter import render_telegram
        result, _ = await _gates["market"].run(collect_market_pulse)
        await _send(update, msg, render_telegram(format_pulse(result)))
    except Exception as e:
        await msg.edit_text(f"❌ {e}")


async def handle_news(update, context):
    if not _allowed(update): return await _deny(update)
    try: limit = int(context.args[0]) if context.args else 10
    except ValueError: limit = 10
    msg = await update.message.reply_text("📡 Loading news…")
    try:
        from majestic.db.state import StateDB
        rows = StateDB().search_news("*", k=limit)
        if not rows:
            await msg.edit_text("No news found. Run /research first."); return
        lines = [f"<b>{i+1}.</b> [{r['source']}] {r['title']}" for i, r in enumerate(rows)]
        await _send(update, msg, "\n".join(lines))
    except Exception as e:
        await msg.edit_text(f"❌ {e}")


async def handle_report(update, context):
    if not _allowed(update): return await _deny(update)
    topic = " ".join(context.args or []).strip()
    if not topic:
        await update.message.reply_text("Usage: /report <topic>"); return
    msg = await update.message.reply_text(f"📝 Generating report: {topic[:60]}…")
    try:
        from majestic.rag import ask
        from majestic.gateway.formatter import render_telegram
        result = await asyncio.to_thread(ask, f"Create detailed report on: {topic}", scope="all")
        await _send(update, msg, render_telegram(result["answer"]))
    except Exception as e:
        await msg.edit_text(f"❌ {e}")


async def handle_skills(update, context):
    if not _allowed(update): return await _deny(update)
    try:
        from majestic.skills.loader import list_skills
        skills = list_skills()
        if not skills:
            await update.message.reply_text("No skills saved yet."); return
        lines = [f"/{s['name']} — {s.get('description','')}" for s in skills]
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")


async def handle_memory(update, context):
    if not _allowed(update): return await _deny(update)
    try:
        from majestic.memory.store import show
        from majestic.gateway.formatter import render_telegram
        await update.message.reply_text(render_telegram(show()), parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")


async def handle_tokens(update, context):
    if not _allowed(update): return await _deny(update)
    from majestic.token_tracker import format_stats
    await update.message.reply_text(f"<pre>{format_stats()}</pre>", parse_mode="HTML")


async def handle_stats(update, context):
    if not _allowed(update): return await _deny(update)
    try:
        from majestic.rag import stats
        s = stats()
        await update.message.reply_text(
            f"📊 <b>Knowledge base</b>\nChunks: {s['chunks']}\nFiles: {s['files']}",
            parse_mode="HTML",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")


async def handle_set(update, context):
    if not _allowed(update): return await _deny(update)
    args = context.args or []
    if len(args) >= 2:
        key, val = args[0].lower(), args[1]
        from majestic.config import set_value, get
        if key == "lang":
            set_value("language", val.upper())
            await update.message.reply_text(f"✅ Language → {val.upper()}")
        elif key == "currency":
            set_value("currency", val.upper())
            await update.message.reply_text(f"✅ Currency → {val.upper()}")
        elif key == "mod":
            set_value("search_mode", val.lower())
            await update.message.reply_text(f"✅ Scope → {val.lower()}")
        else:
            await update.message.reply_text("Usage: /set lang|currency|mod <value>")
    else:
        from majestic.config import get
        await update.message.reply_text(
            f"lang={get('language','EN')}  currency={get('currency','USD')}  mod={get('search_mode','all')}"
        )


async def handle_logs(update, context):
    if not _allowed(update): return await _deny(update)
    try:
        from majestic.error_logger import get_errors
        lines = [f"[{e['ts'][:16]}] {e['source']}: {e['message']}" for e in get_errors(10)]
        text = "\n".join(lines) if lines else "No errors logged."
        await update.message.reply_text(f"<pre>{text[:3000]}</pre>", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")


async def handle_remind(update, context):
    if not _allowed(update): return await _deny(update)
    text = " ".join(context.args or []).strip()
    if not text:
        await update.message.reply_text("Usage: /remind <text with date>"); return
    try:
        from majestic.reminders import extract_reminder_intent, add_reminder, format_reminder
        intent = extract_reminder_intent(text)
        if not intent:
            await update.message.reply_text("❌ Could not parse date/time."); return
        r = add_reminder(intent["title"], intent["dt"])
        await update.message.reply_text(f"✅ {format_reminder(r)}")
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")


async def handle_reminders(update, context):
    if not _allowed(update): return await _deny(update)
    from majestic.reminders import list_reminders, format_reminder
    items = list_reminders()
    if not items:
        await update.message.reply_text("No active reminders."); return
    await update.message.reply_text(
        "\n".join(f"{i+1}. {format_reminder(r)}" for i, r in enumerate(items))
    )


async def handle_schedule(update, context):
    if not _allowed(update): return await _deny(update)
    args = context.args or []
    sub  = args[0].lower() if args else ""

    if sub == "list":
        from majestic.cron.jobs import list_schedules
        rows = list_schedules()
        if not rows:
            await update.message.reply_text("No schedules. Add with /schedule add <description>")
            return
        lines = []
        for r in rows:
            status = "✅" if r["enabled"] else "⏸"
            lines.append(f"{status} <b>{r['id']}.</b> {r['name']} — <code>{r['cron_expr']}</code>\n"
                         f"   {r['prompt']} → {r['delivery_target']}\n"
                         f"   Next: {(r['next_run'] or '—')[:16]}")
        await update.message.reply_text("\n\n".join(lines), parse_mode="HTML")

    elif sub == "remove":
        if len(args) < 2 or not args[1].isdigit():
            await update.message.reply_text("Usage: /schedule remove <id>"); return
        from majestic.cron.jobs import remove_schedule
        ok = remove_schedule(int(args[1]))
        await update.message.reply_text("✅ Removed." if ok else "❌ Schedule not found.")

    elif sub == "add":
        text = " ".join(args[1:]).strip()
        if not text:
            await update.message.reply_text(
                "Usage: /schedule add <description>\n"
                "Example: /schedule add every day at 9am generate briefing\n"
                "Example: /schedule add every monday at 8am do research and send to telegram"
            ); return
        msg = await update.message.reply_text("⏳ Parsing schedule…")
        try:
            from majestic.cron.jobs import nl_to_schedule, add_schedule
            parsed = await asyncio.to_thread(nl_to_schedule, text)
            target = parsed.get("target", "telegram")
            s = add_schedule(
                name=parsed["name"],
                cron_expr=parsed["cron"],
                prompt=parsed["prompt"],
                delivery_target=target,
            )
            await msg.edit_text(
                f"✅ Schedule added:\n"
                f"<b>{s['name']}</b> — <code>{s['cron_expr']}</code>\n"
                f"Task: {s['prompt']}\n"
                f"Deliver to: {s['delivery_target']}\n"
                f"Next run: {(s['next_run'] or '—')[:16]}",
                parse_mode="HTML",
            )
        except Exception as e:
            await msg.edit_text(f"❌ Could not parse schedule: {e}")

    else:
        await update.message.reply_text(
            "/schedule list\n/schedule add <description>\n/schedule remove <id>"
        )


async def handle_voice(update, context):
    """Transcribe voice/audio message via Whisper and run through agent."""
    if not _allowed(update): return await _deny(update)
    from majestic import config as cfg
    if not cfg.get("telegram.voice_transcription", True):
        await update.message.reply_text("🎙 Voice transcription is disabled.")
        return

    voice = update.message.voice or update.message.audio
    if not voice:
        return

    msg = await update.message.reply_text("🎙 Transcribing…")
    try:
        import tempfile, os
        tg_file = await context.bot.get_file(voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name
        await tg_file.download_to_drive(tmp_path)

        transcript = await asyncio.to_thread(_whisper_transcribe, tmp_path)
        os.unlink(tmp_path)

        if not transcript:
            await msg.edit_text("❌ Could not transcribe audio.")
            return

        await msg.edit_text(f"🎙 <i>{transcript}</i>\n\n⏳ Thinking…", parse_mode="HTML")
        uid     = update.effective_user.id
        history = _history.get(uid, [])
        session_id = await asyncio.to_thread(_get_session, uid)

        from majestic.agent.loop import AgentLoop
        result = await asyncio.to_thread(AgentLoop().run, transcript, session_id, history)
        answer = result.get("answer", "")

        from majestic.gateway.formatter import render_telegram
        text = render_telegram(answer) or "—"
        await msg.edit_text(text, parse_mode="HTML")

        if answer:
            history = list(history) + [(transcript, answer)]
            _history[uid] = history[-_SESSION_MAX:]
    except Exception as e:
        await msg.edit_text(f"❌ {e}")


def _whisper_transcribe(path: str) -> str:
    import os
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key:
        from openai import OpenAI
        client = OpenAI(api_key=openai_key)
        with open(path, "rb") as f:
            resp = client.audio.transcriptions.create(model="whisper-1", file=f)
        return resp.text.strip()
    # Fallback: faster-whisper local
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(path)
        return " ".join(s.text for s in segments).strip()
    except ImportError:
        raise RuntimeError("No transcription backend available. Set OPENAI_API_KEY or install faster-whisper.")


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
        from majestic.rag import index_file
        n = await asyncio.to_thread(index_file, dest)
        await msg.edit_text(f"✅ Indexed {doc.file_name} — {n} chunks")
    except Exception as e:
        await msg.edit_text(f"❌ {e}")
