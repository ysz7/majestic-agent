#!/usr/bin/env python3
"""
Telegram bot — primary interface for Parallax AI
Run: python bot.py

Commands:
  /start      — welcome + command list
  /research   — collect HN + Reddit + GitHub + auto-summary
  /ask <q>    — RAG query
  /ideas      — 5 business ideas
  /market     — crypto + stocks + forex
  /briefing   — daily briefing
  /remind     — add a reminder
  /reminders  — list active reminders
  /stats      — knowledge base stats
  /report     — generate a report on a topic

File upload: send any .pdf .docx .csv .txt .md → auto-indexed
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from telegram import Update, Document, BotCommand, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode
from core.formatter import render_telegram


def _fmt_sources(sources: list, mod: str = "all") -> str:
    """Format source list into a compact footer line for Telegram."""
    if not sources:
        return ""
    doc_sources   = [s for s in sources if not s.startswith("intel:")]
    intel_sources = [s for s in sources if s.startswith("intel:")]
    parts = []
    if doc_sources:
        parts.append(f"📄 <i>{', '.join(doc_sources)}</i>")
    if intel_sources and mod in ("all", "intel"):
        labels = [s.replace("intel:", "") for s in intel_sources]
        parts.append(f"🔍 <i>{', '.join(labels)}</i>")
    return "\n" + " │ ".join(parts) if parts else ""

TG_MAX = 4096


def _split_text(text: str, max_len: int = TG_MAX) -> list[str]:
    """Split text into chunks ≤ max_len chars, preferring paragraph then line boundaries."""
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        split_at = text.rfind("\n\n", 0, max_len)
        if split_at < max_len // 3:
            split_at = text.rfind("\n", 0, max_len)
        if split_at < 0:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


async def _send_long(
    update: Update,
    msg,
    text: str,
    parse_mode: str = ParseMode.HTML,
    footer: str = "",
) -> None:
    """Edit `msg` with the first chunk; send remaining chunks as new replies.
    `footer` is appended to the last chunk only.
    """
    chunks = _split_text(text, TG_MAX - len(footer) if footer else TG_MAX)
    if not chunks:
        await msg.edit_text("(empty)", parse_mode=parse_mode)
        return
    for i, chunk in enumerate(chunks):
        payload = chunk + (footer if i == len(chunks) - 1 else "")
        if i == 0:
            await msg.edit_text(payload, parse_mode=parse_mode)
        else:
            await update.message.reply_text(payload, parse_mode=parse_mode)


logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Supports single ID or comma-separated list: "123456,789012"
_raw_ids = os.getenv("TELEGRAM_ALLOWED_USER_ID", "")
ALLOWED_UIDS: set[int] = {int(x.strip()) for x in _raw_ids.split(",") if x.strip().isdigit()}

SUPPORTED_EXTS = {".pdf", ".docx", ".csv", ".txt", ".md"}

INBOX_DIR = Path(__file__).parent / "data" / "inbox"
INBOX_DIR.mkdir(parents=True, exist_ok=True)

WELCOME = """👋 <b>Parallax</b>

AI Research &amp; Intelligence Agent — RAG knowledge base + web intelligence.

<b>Commands:</b>
/research — collect HN + Reddit + GitHub
/ask &lt;question&gt; — search knowledge base
/ideas — 5 business ideas
/market — crypto + stocks + forex
/briefing [N] — world briefing + segment map + predictions (default 14 days)
/predict [N] — cross-niche predictions with probabilities (default 14 days)
/news [N] — last N news items (default 10)
/tokens — Anthropic token usage &amp; cost
/set lang EN — set response language (EN, RU, DE, ES, ...)
/set mod all — search scope: all | docs | intel
/logs — recent error log
/rss — manage RSS feeds (add/list/remove)
/remind &lt;text&gt; — add reminder
/reminders — list reminders
/reports — list saved reports
/reports pdf &lt;N&gt; — export report to PDF
/stats — knowledge base stats
/report &lt;topic&gt; — generate report

Send a file to index it into the knowledge base.
"""

# Persistent reply keyboard shown below the message input
MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[
        ["/research", "/briefing"],
        ["/predict",  "/ideas"],
        ["/market",   "/news"],
        ["/tokens",   "/reports"],
        ["/stats",    "/logs"],
        ["/remind",   "/reminders"],
        ["/logs",     "/start"],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)

# Per-user conversation history: {user_id: [(user_msg, assistant_msg), ...]}
_sessions: dict[int, list[tuple[str, str]]] = {}
_SESSION_MAX = 10


# ── Shared execution gate ──────────────────────────────────────────────────────
# Prevents concurrent execution of heavy commands.
# If user1 runs /research and user2 runs /research while it's in progress,
# user2 waits and receives the same result — no duplicate work.

class _Gate:
    """Run a blocking function once at a time; concurrent callers wait and share the result."""

    def __init__(self, name: str):
        self.name    = name
        self._lock   = asyncio.Lock()
        self._busy   = False
        self._done   = asyncio.Event()
        self._done.set()   # starts as "free"
        self._result = None
        self._error: Exception | None = None

    async def run(self, fn, *args):
        """
        Returns (result, is_fresh):
          is_fresh=True  — this caller executed fn
          is_fresh=False — this caller waited and received a shared result
        """
        async with self._lock:
            if not self._busy:
                # Become the runner
                self._busy  = True
                self._error = None
                self._done.clear()
                am_runner = True
            else:
                am_runner = False

        if am_runner:
            try:
                self._result = await asyncio.to_thread(fn, *args)
            except Exception as e:
                self._error  = e
                self._result = None
            finally:
                async with self._lock:
                    self._busy = False
                self._done.set()
            if self._error:
                raise self._error
            return self._result, True
        else:
            # Wait for runner to finish
            await self._done.wait()
            if self._error:
                raise self._error
            return self._result, False


# One gate per heavy command
_gates: dict[str, _Gate] = {
    "research":    _Gate("research"),
    "briefing":    _Gate("briefing"),
    "ideas":       _Gate("ideas"),
    "market":      _Gate("market"),
    "predictions": _Gate("predictions"),
    "flows":       _Gate("flows"),
}


# ── Access control ─────────────────────────────────────────────────────────────

def _allowed(update: Update) -> bool:
    if not ALLOWED_UIDS:
        return True
    return update.effective_user and update.effective_user.id in ALLOWED_UIDS


async def _deny(update: Update):
    await update.message.reply_text("⛔ Access denied.")


# ── Telegram notify (called by core/agent.py) ──────────────────────────────────
_bot_app: Application | None = None


def _sync_notify(text: str):
    """Thread-safe notification from background threads (agent, reminders).
    Splits long messages into TG_MAX-char chunks automatically.
    """
    if not _bot_app or not ALLOWED_UIDS:
        print(f"[notify] {text}")
        return
    chunks = _split_text(render_telegram(text))
    loop = asyncio.get_event_loop()
    for uid in ALLOWED_UIDS:
        for chunk in chunks:
            try:
                coro = _bot_app.bot.send_message(
                    chat_id=uid,
                    text=chunk,
                    parse_mode=ParseMode.HTML,
                )
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(coro, loop)
                else:
                    loop.run_until_complete(coro)
            except Exception as e:
                logger.error(f"[notify] send to {uid} failed: {e}")


# ── Handlers ───────────────────────────────────────────────────────────────────

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return await _deny(update)
    await update.message.reply_text(WELCOME, parse_mode=ParseMode.HTML, reply_markup=MAIN_MENU)


async def handle_research(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return await _deny(update)

    gate = _gates["research"]
    if gate._busy:
        msg = await update.message.reply_text("⏳ Research already in progress by another user — waiting for result...")
    else:
        msg = await update.message.reply_text("⏳ Collecting data from all sources...")

    try:
        from core.intel import collect_and_index
        from core.trends import quick_summary_from_new

        def _run():
            return collect_and_index()

        result, is_fresh = await gate.run(_run)

        new = result["total_new"]
        skipped = result["total_seen"]
        by_src = result.get("by_source", {})
        src_lines = "\n".join(f"  {k}: {v}" for k, v in by_src.items())
        shared_tag = "" if is_fresh else "\n<i>(shared result — was already running)</i>"
        status = f"✅ Done: <b>{new}</b> new items (skipped {skipped} duplicates)\n{src_lines}{shared_tag}"

        new_items = result.get("new_items", [])
        if new_items and is_fresh:
            await msg.edit_text(status + "\n\n⏳ Generating summary...", parse_mode=ParseMode.HTML)
            summary = await asyncio.to_thread(quick_summary_from_new, new_items)
            full = status + "\n\n" + render_telegram(summary)
        elif new_items and not is_fresh:
            # Summary was already generated by the runner — just show status
            full = status
        else:
            full = status + "\n\n📭 No new items to summarize."

        await _send_long(update, msg, full)

        # Refresh market snapshot after research so briefings have fresh prices
        try:
            from core.market_pulse import collect_market_pulse, format_pulse
            market_data = await asyncio.to_thread(collect_market_pulse)
            await update.message.reply_text(format_pulse(market_data))
        except Exception as _me:
            logger.warning(f"[research] market refresh failed: {_me}")

    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")


async def handle_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return await _deny(update)
    question = " ".join(context.args or [])
    if not question:
        await update.message.reply_text("Usage: /ask <your question>")
        return
    uid = update.effective_user.id
    history = _sessions.get(uid, [])
    msg = await update.message.reply_text("⏳ Searching knowledge base...")
    try:
        from core.rag_engine import ask
        from core.config import get_mod
        result = await asyncio.to_thread(ask, question, None, history, get_mod())
        answer = render_telegram(result["answer"])
        footer = _fmt_sources(result.get("sources", []), get_mod())
        await _send_long(update, msg, answer, footer=footer)
        # Update session history
        _sessions.setdefault(uid, []).append((question, result["answer"]))
        if len(_sessions[uid]) > _SESSION_MAX:
            _sessions[uid] = _sessions[uid][-_SESSION_MAX:]
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")


async def handle_ideas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return await _deny(update)

    gate = _gates["ideas"]
    if gate._busy:
        msg = await update.message.reply_text("⏳ Ideas are being generated by another user — waiting...")
    else:
        msg = await update.message.reply_text("⏳ Generating 5 business ideas...")
    try:
        from core.agent import generate_ideas
        ideas, is_fresh = await gate.run(generate_ideas, True)
        tag = "" if is_fresh else "\n\n<i>(shared result)</i>"
        await _send_long(update, msg, render_telegram(ideas), footer=tag)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")


async def handle_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return await _deny(update)

    gate = _gates["market"]
    if gate._busy:
        msg = await update.message.reply_text("⏳ Market data is being fetched — waiting for result...")
    else:
        msg = await update.message.reply_text("⏳ Fetching market data...")
    try:
        from core.market_pulse import collect_market_pulse, format_pulse
        data, _ = await gate.run(collect_market_pulse)
        await msg.edit_text(format_pulse(data)[:4096])
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")


async def handle_briefing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return await _deny(update)

    days = 14
    if context.args:
        try:
            days = int(context.args[0])
        except ValueError:
            pass

    gate = _gates["briefing"]
    if gate._busy:
        msg = await update.message.reply_text(f"⏳ Briefing is being generated by another user — waiting...")
    else:
        msg = await update.message.reply_text(f"⏳ Generating briefing (last {days} days)...")
    try:
        from core.trends import generate_briefing
        briefing, is_fresh = await gate.run(generate_briefing, days)
        tag = "" if is_fresh else "\n\n<i>(shared result)</i>"
        await _send_long(update, msg, render_telegram(briefing), footer=tag)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")


async def handle_predict(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return await _deny(update)

    days = 14
    if context.args:
        try:
            days = int(context.args[0])
        except ValueError:
            pass

    gate = _gates["predictions"]
    if gate._busy:
        msg = await update.message.reply_text("⏳ Predictions are being generated — waiting...")
    else:
        msg = await update.message.reply_text(f"⏳ Generating predictions (last {days} days)...")
    try:
        from core.trends import generate_predictions
        result, is_fresh = await gate.run(generate_predictions, days)
        tag = "" if is_fresh else "\n\n<i>(shared result)</i>"
        await _send_long(update, msg, render_telegram(result), footer=tag)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")


async def handle_flows(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return await _deny(update)

    days = 14
    if context.args:
        try:
            days = int(context.args[0])
        except ValueError:
            pass

    gate = _gates["flows"]
    if gate._busy:
        msg = await update.message.reply_text("⏳ Money flows analysis is already running — waiting...")
    else:
        msg = await update.message.reply_text(f"⏳ Analyzing money flows (last {days} days)...")
    try:
        from core.trends import generate_money_flows
        result, is_fresh = await gate.run(generate_money_flows, days)
        tag = "" if is_fresh else "\n\n<i>(shared result)</i>"
        await _send_long(update, msg, render_telegram(result), footer=tag)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")


async def handle_remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return await _deny(update)
    text = " ".join(context.args or [])
    if not text:
        await update.message.reply_text(
            "Usage: /remind <text with date>\n"
            "Example: /remind tomorrow at 10:00 call Ivan"
        )
        return
    from core.reminders import extract_reminder_intent, add_reminder, format_reminder, parse_date
    import re
    intent = extract_reminder_intent(text)
    if not intent:
        dt = parse_date(text)
        if dt:
            title = re.sub(
                r"(завтра|сегодня|послезавтра|через .+?|в \d{1,2}[:.]\d{2}|"
                r"tomorrow|today|in \d+ \w+|on \w+|\d{1,2}[:.]\d{2})",
                "", text, flags=re.IGNORECASE,
            ).strip(" —-–:,")
            intent = {"title": title or text, "dt": dt}
        else:
            await update.message.reply_text(f"⚠️ Could not parse date from: «{text}»\nTry: /remind tomorrow at 10:00 call Ivan")
            return
    r = add_reminder(intent["title"], intent["dt"])
    await update.message.reply_text(f"✅ Reminder added:\n{format_reminder(r)}")


async def handle_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return await _deny(update)
    from core.reminders import list_reminders, format_reminder
    items = list_reminders()
    if not items:
        await update.message.reply_text("📭 No active reminders.")
        return
    lines = [f"<b>Active reminders ({len(items)}):</b>\n"]
    for r in items:
        lines.append(format_reminder(r))
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def handle_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return await _deny(update)
    arg = context.args[0] if context.args else "10"
    limit = int(arg) if arg.isdigit() else 10
    from core.intel import load_feed
    items = load_feed(limit=limit * 3)  # fetch more, sort by CCW, trim
    if not items:
        await update.message.reply_text("📭 No news yet. Run /research first.")
        return

    from core.ccw import ccw_label
    from core.formatter import _esc

    def _score_int(item):
        v = item.get("score") or item.get("stars") or 0
        try:
            return int(str(v).replace(",", "").split()[0])
        except Exception:
            return 0

    # Sort by CCW desc, then engagement
    items = sorted(
        items,
        key=lambda x: (x.get("ccw", 0), _score_int(x)),
        reverse=True,
    )[:limit]

    SOURCE_ICONS = {
        "hackernews":      "🟠 HN",
        "reddit":          "🔴 Reddit",
        "github_trending": "🐙 GitHub",
        "producthunt":     "🔶 PH",
        "mastodon":        "🐘 Mastodon",
        "devto":           "💻 Dev.to",
        "google_trends":   "📈 Trends",
    }

    lines = [f"<b>Latest {len(items)} news (by CCW):</b>\n"]
    for i, item in enumerate(items, 1):
        src   = item.get("source", "")
        icon  = SOURCE_ICONS.get(src, src)
        title = item.get("title", "")
        url   = item.get("url", "")
        score = item.get("score") or item.get("stars") or ""
        score_str = f" <code>[{score}]</code>" if score else ""
        ccw = item.get("ccw", 0)
        ccw_str = f" <b>{ccw_label(ccw)}</b>" if ccw >= 5 else ""
        lines.append(f"{i}. [{icon}] <b>{_esc(title)}</b>{score_str}{ccw_str}")
        if item.get("ccw_reason"):
            lines.append(f"   <i>↳ {_esc(item['ccw_reason'])}</i>")
        if url:
            lines.append(f"   {url}")

    await update.message.reply_text("\n".join(lines)[:4096], parse_mode=ParseMode.HTML)


async def handle_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return await _deny(update)
    from core.rag_engine import stats, delete_file, DONE_DIR
    args = context.args or []

    s = await asyncio.to_thread(stats)
    intel_files = [f for f in s["file_list"] if f.startswith("intel:")]
    real_files  = [f for f in s["file_list"] if not f.startswith("intel:")]

    # /stats del <N>
    if args and args[0] == "del":
        if len(args) < 2 or not args[1].isdigit():
            await update.message.reply_text("Usage: /stats del &lt;number&gt;", parse_mode=ParseMode.HTML)
            return
        idx = int(args[1]) - 1
        if not real_files or idx < 0 or idx >= len(real_files):
            await update.message.reply_text("Invalid number. Use /stats to see the list.")
            return
        target = real_files[idx]
        n = await asyncio.to_thread(delete_file, target)
        phys = DONE_DIR / target
        if phys.exists():
            phys.unlink()
        await update.message.reply_text(
            f"✅ Deleted: <code>{target}</code> ({n} chunks removed)",
            parse_mode=ParseMode.HTML,
        )
        return

    # Show stats
    text = (
        f"📊 <b>Knowledge base</b>\n"
        f"Chunks: <code>{s['chunks']}</code>"
    )
    if intel_files:
        text += f"\n\n<b>Intel sources ({len(intel_files)}):</b>\n"
        text += "\n".join(f"• <i>{f}</i>" for f in sorted(intel_files))
    if real_files:
        text += f"\n\n<b>Indexed files ({len(real_files)}):</b>\n"
        text += "\n".join(f"{i}. <code>{f}</code>" for i, f in enumerate(real_files, 1))
        text += "\n\n<i>To delete: /stats del &lt;number&gt;</i>"
    await update.message.reply_text(text[:4096], parse_mode=ParseMode.HTML)


async def handle_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return await _deny(update)
    from core.rag_engine import EXPORT_DIR
    args = context.args or []

    files = sorted(EXPORT_DIR.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        await update.message.reply_text("📭 No reports yet.")
        return

    # /reports del <N>
    if args and args[0] == "del":
        if len(args) < 2 or not args[1].isdigit():
            await update.message.reply_text("Usage: /reports del &lt;number&gt;", parse_mode=ParseMode.HTML)
            return
        idx = int(args[1]) - 1
        if idx < 0 or idx >= len(files):
            await update.message.reply_text("Invalid number.")
            return
        files[idx].unlink()
        await update.message.reply_text(f"✅ Deleted: <code>{files[idx].name}</code>", parse_mode=ParseMode.HTML)
        return

    # /reports view <N>
    if args and args[0] == "view":
        if len(args) < 2 or not args[1].isdigit():
            await update.message.reply_text("Usage: /reports view &lt;number&gt;", parse_mode=ParseMode.HTML)
            return
        idx = int(args[1]) - 1
        if idx < 0 or idx >= len(files):
            await update.message.reply_text("Invalid number.")
            return
        f = files[idx]
        content = f.read_text(encoding="utf-8")
        rendered = render_telegram(content)
        header = f"<b>{f.name}</b>\n\n"
        # Telegram limit 4096 chars; send in chunks if needed
        full = header + rendered
        for i in range(0, min(len(full), 12000), 4096):
            chunk = full[i:i+4096]
            if chunk:
                await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)
        return

    # /reports pdf <N>
    if args and args[0] == "pdf":
        if len(args) < 2 or not args[1].isdigit():
            await update.message.reply_text("Usage: /reports pdf &lt;number&gt;", parse_mode=ParseMode.HTML)
            return
        idx = int(args[1]) - 1
        if idx < 0 or idx >= len(files):
            await update.message.reply_text("Invalid number.")
            return
        f = files[idx]
        msg = await update.message.reply_text(f"⏳ Exporting <code>{f.name}</code> to PDF...", parse_mode=ParseMode.HTML)
        try:
            from core.exporter import export_md_to_pdf
            pdf_path = await asyncio.to_thread(export_md_to_pdf, f)
            with open(pdf_path, "rb") as pdf_file:
                await update.message.reply_document(
                    document=pdf_file,
                    filename=pdf_path.name,
                    caption=f"📄 {f.stem}",
                )
            await msg.delete()
        except RuntimeError as e:
            await msg.edit_text(f"⚠️ {e}", parse_mode=None)
        except Exception as e:
            await msg.edit_text(f"❌ Export error: {e}")
        return

    from datetime import datetime
    lines = [f"<b>Saved reports ({len(files)}):</b>\n"]
    # Display oldest first so newest appears at bottom
    for i, f in reversed(list(enumerate(files, 1))):
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        size_kb = f.stat().st_size / 1024
        lines.append(f"{i}. <code>{f.name}</code>\n   <i>{mtime}  {size_kb:.1f} KB</i>")
    lines.append("\n<i>View: /reports view &lt;number&gt;  |  Delete: /reports del &lt;number&gt;</i>")
    await update.message.reply_text("\n".join(lines)[:4096], parse_mode=ParseMode.HTML)


async def handle_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return await _deny(update)
    topic = " ".join(context.args or [])
    if not topic:
        await update.message.reply_text("Usage: /report <topic>")
        return
    from core.config import get_mod
    scope = get_mod()
    scope_label = {"all": "all sources", "docs": "local documents", "intel": "research intel"}
    msg = await update.message.reply_text(
        f"⏳ Generating report on: {topic}\n<i>Source: {scope_label.get(scope, scope)}</i>",
        parse_mode=ParseMode.HTML,
    )
    try:
        from core.rag_engine import ask, EXPORT_DIR
        from datetime import datetime
        question = (
            f"Create a detailed structured report on the topic: «{topic}». "
            "Include all relevant data from the documents. "
            "Divide into sections with headings."
        )
        result = await asyncio.to_thread(ask, question, None, None, scope)

        # If RAG found nothing useful — enrich with web search
        web_sources = []
        _no_data = (
            "no relevant information", "не найдено", "no data", "нет данных", "not found in",
            "ограниченная информация", "limited information", "не содержит", "отсутствует",
            "не представлена", "только косвенно", "недостаточно", "нет прямой",
            "контекст не содержит", "предоставленный контекст", "в контексте отсутствует",
        )
        sources = result.get("sources", [])
        low_quality = any(m in result["answer"].lower() for m in _no_data)
        intel_only = bool(sources) and all(str(s).startswith("intel:") for s in sources)
        if low_quality or intel_only:
            await msg.edit_text(
                f"⏳ No local data — searching the web for: <i>{topic}</i>...",
                parse_mode=ParseMode.HTML,
            )
            from core.web_search import search as web_search
            web_results = await asyncio.to_thread(web_search, topic, 6)
            if web_results:
                from core.rag_engine import llm
                from core.config import get_lang
                from langchain_core.messages import HumanMessage
                lang = get_lang()
                web_ctx = "\n\n---\n\n".join(
                    f"[{r['title']}]\n{r['content']}\nSource: {r['url']}" for r in web_results
                )
                web_prompt = (
                    f"Create a detailed structured report on: «{topic}».\n"
                    f"Use ONLY the web search results below. Respond in {lang}. "
                    f"Use ## headings, bullet points, bold key facts.\n\n"
                    f"{web_ctx[:6000]}\n\nReport:"
                )
                response = await asyncio.to_thread(llm.invoke, [HumanMessage(content=web_prompt)])
                from core.token_tracker import track_response
                track_response(response, "report.web")
                result = {"answer": response.content, "sources": []}
                web_sources = [r["url"] for r in web_results if r.get("url")]

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = topic[:40].replace(" ", "_").replace("/", "-")
        out = EXPORT_DIR / f"report_{slug}_{ts}.md"
        content = f"# Report: {topic}\n_Created: {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n\n"
        content += result["answer"]
        all_sources = list(result.get("sources", [])) + web_sources
        if all_sources:
            content += f"\n\n---\n**Sources:** {', '.join(all_sources)}"
        out.write_text(content, encoding="utf-8")

        reply = render_telegram(result["answer"])
        footer = _fmt_sources(all_sources, scope)
        await _send_long(update, msg, f"✅ Saved: <code>{out.name}</code>\n\n{reply}", footer=footer)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle plain text messages as RAG queries."""
    if not _allowed(update):
        return await _deny(update)
    question = update.message.text.strip()
    if not question:
        return
    uid = update.effective_user.id
    history = _sessions.get(uid, [])
    msg = await update.message.reply_text("⏳ Searching...")
    try:
        from core.rag_engine import ask
        from core.config import get_mod
        result = await asyncio.to_thread(ask, question, None, history, get_mod())

        # Web fallback if RAG has no useful data
        _no_data_markers = (
            "no relevant information", "не найдено", "no data", "нет данных", "not found in",
            "ограниченная информация", "limited information", "не содержит", "отсутствует",
            "не представлена", "только косвенно", "недостаточно", "нет прямой",
            "контекст не содержит", "предоставленный контекст", "в контексте отсутствует",
        )
        sources = result.get("sources", [])
        low_quality = any(m in result["answer"].lower() for m in _no_data_markers)
        intel_only = bool(sources) and all(str(s).startswith("intel:") for s in sources)
        if low_quality or intel_only:
            await msg.edit_text("🌐 Searching the web...")
            from core.web_search import search_and_answer
            web_result = await asyncio.to_thread(search_and_answer, question)
            if web_result:
                result = web_result

        answer = render_telegram(result["answer"])
        footer = _fmt_sources(result.get("sources", []), get_mod())
        await _send_long(update, msg, answer, footer=footer)
        # Update session history
        _sessions.setdefault(uid, []).append((question, result["answer"]))
        if len(_sessions[uid]) > _SESSION_MAX:
            _sessions[uid] = _sessions[uid][-_SESSION_MAX:]
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")


async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return await _deny(update)
    query = " ".join(context.args or [])
    if not query:
        await update.message.reply_text("Usage: /search <query>")
        return
    msg = await update.message.reply_text(f"🌐 Searching: {query[:60]}...")
    try:
        from core.web_search import search_and_answer
        result = await asyncio.to_thread(search_and_answer, query)
        if not result:
            await msg.edit_text("❌ No results found.")
            return
        answer = render_telegram(result["answer"])
        sources = result.get("sources", [])
        footer = "\n\n🔗 <i>" + " | ".join(sources[:3]) + "</i>" if sources else ""
        await _send_long(update, msg, f"🌐 <b>Web search</b>\n\n{answer}", footer=footer)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")


async def handle_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return await _deny(update)
    args = context.args or []

    if args and args[0].lower() == "reset":
        # Ask for confirmation via a follow-up message
        await update.message.reply_text(
            "⚠️ Reset token counter? Reply /tokens confirm to proceed."
        )
        return

    if args and args[0].lower() == "confirm":
        from core.token_tracker import reset as token_reset
        token_reset()
        await update.message.reply_text("✅ Token counter reset.")
        return

    from core.token_tracker import format_stats
    text = format_stats()
    await update.message.reply_text(f"<pre>{text}</pre>", parse_mode=ParseMode.HTML)


async def handle_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return await _deny(update)
    from core.error_logger import format_errors
    text = format_errors(limit=15)
    await update.message.reply_text(f"<pre>{text}</pre>", parse_mode=ParseMode.HTML)


async def handle_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return await _deny(update)
    args = context.args or []
    from core.config import set_lang, get_lang, set_currency, get_currency, set_mod, get_mod
    if len(args) < 2:
        mod = get_mod()
        mod_desc = {"all": "docs + intel", "docs": "local documents only", "intel": "research intel only"}
        await update.message.reply_text(
            "⚙️ <b>Settings</b>\n\n"
            f"Language:  <code>{get_lang()}</code>\n"
            f"Currency:  <code>{get_currency()}</code>\n"
            f"Mod:       <code>{mod}</code>  <i>({mod_desc.get(mod, mod)})</i>\n\n"
            "• <code>/set lang EN</code> — response language (EN, RU, ES, DE, ...)\n"
            "• <code>/set currency USD</code> — prices currency (USD, EUR, GBP, ...)\n"
            "• <code>/set mod all</code> — search scope: <code>all</code> | <code>docs</code> | <code>intel</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    key, value = args[0].lower(), args[1]
    if key == "lang":
        set_lang(value.upper())
        await update.message.reply_text(f"✅ Language set to <code>{get_lang()}</code>", parse_mode=ParseMode.HTML)
    elif key == "currency":
        set_currency(value.upper())
        await update.message.reply_text(f"✅ Currency set to <code>{get_currency()}</code>", parse_mode=ParseMode.HTML)
    elif key == "mod":
        try:
            set_mod(value.lower())
            mod = get_mod()
            mod_desc = {"all": "docs + intel", "docs": "local documents only", "intel": "research intel only"}
            await update.message.reply_text(
                f"✅ Search mode set to <b>{mod}</b> — {mod_desc.get(mod, mod)}",
                parse_mode=ParseMode.HTML,
            )
        except ValueError as e:
            await update.message.reply_text(f"⚠️ {e}", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(
            f"⚠️ Unknown setting: <code>{key}</code>\nAvailable: lang, currency, mod",
            parse_mode=ParseMode.HTML,
        )


async def handle_rss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _allowed(update):
        return await _deny(update)
    from core.rss import list_feeds, add_feed, remove_feed
    from core.formatter import _esc
    args = context.args or []
    sub = args[0].lower() if args else "list"

    if sub == "list" or not args:
        feeds = list_feeds()
        if not feeds:
            await update.message.reply_text("📭 No RSS feeds configured.\nAdd one: /rss add <url>")
            return
        lines = [f"<b>RSS feeds ({len(feeds)}):</b>\n"]
        for i, f in enumerate(feeds, 1):
            lines.append(f"{i}. <b>{_esc(f['name'])}</b>")
            lines.append(f"   <code>{f['url']}</code>")
        lines.append("\n<i>Remove: /rss remove &lt;number&gt;</i>")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    elif sub == "add":
        url = args[1] if len(args) > 1 else ""
        if not url:
            await update.message.reply_text("Usage: /rss add <url>")
            return
        msg = await update.message.reply_text(f"⏳ Validating feed...")
        try:
            entry = await asyncio.to_thread(add_feed, url)
            await msg.edit_text(
                f"✅ Added: <b>{_esc(entry['name'])}</b>\n<code>{entry['url']}</code>",
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            await msg.edit_text(f"⚠️ {e}")

    elif sub == "remove":
        n_str = args[1] if len(args) > 1 else ""
        if not n_str.isdigit():
            await update.message.reply_text("Usage: /rss remove <number>")
            return
        try:
            removed = remove_feed(int(n_str))
            await update.message.reply_text(f"✅ Removed: <b>{_esc(removed['name'])}</b>", parse_mode=ParseMode.HTML)
        except Exception as e:
            await update.message.reply_text(f"⚠️ {e}")

    else:
        await update.message.reply_text("Usage: /rss list | /rss add &lt;url&gt; | /rss remove &lt;N&gt;", parse_mode=ParseMode.HTML)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Download and index uploaded files."""
    if not _allowed(update):
        return await _deny(update)
    doc: Document = update.message.document
    if not doc:
        return

    fname = doc.file_name or "upload"
    ext = Path(fname).suffix.lower()
    if ext not in SUPPORTED_EXTS:
        await update.message.reply_text(
            f"⚠️ Unsupported format: <code>{ext}</code>\nSupported: {', '.join(SUPPORTED_EXTS)}",
            parse_mode=ParseMode.HTML,
        )
        return

    msg = await update.message.reply_text(f"⏳ Downloading {fname}...")
    try:
        file = await context.bot.get_file(doc.file_id)
        dest = INBOX_DIR / fname
        # Avoid overwriting
        if dest.exists():
            from datetime import datetime
            dest = INBOX_DIR / f"{Path(fname).stem}_{int(datetime.now().timestamp())}{ext}"
        await file.download_to_drive(str(dest))

        await msg.edit_text(f"⏳ Indexing {fname}...")

        from core.rag_engine import index_file, DONE_DIR
        import shutil
        n = await asyncio.to_thread(index_file, dest)

        # Move to processed
        processed_dest = DONE_DIR / dest.name
        shutil.move(str(dest), str(processed_dest))

        if n:
            await msg.edit_text(f"✅ <b>{fname}</b> — {n} chunks added", parse_mode=ParseMode.HTML)
        else:
            await msg.edit_text(f"⚠️ <b>{fname}</b> — could not index (empty or unsupported)", parse_mode=ParseMode.HTML)
    except Exception as e:
        await msg.edit_text(f"❌ Error indexing {fname}: {e}")


# ── Background services ────────────────────────────────────────────────────────

def _start_auto_research():
    interval_min = int(os.getenv("AUTO_RESEARCH_INTERVAL", "0"))
    if interval_min <= 0:
        return
    import threading, time

    def _loop():
        while True:
            time.sleep(interval_min * 60)
            try:
                from core.intel import collect_and_index
                from core.trends import quick_summary_from_new
                result = collect_and_index()
                new_items = result.get("new_items", [])
                if new_items:
                    summary = quick_summary_from_new(new_items)
                    _sync_notify(f"🔄 *Auto-research:* {result['total_new']} new items\n\n{summary}")
            except Exception as e:
                logger.error(f"[auto-research] {e}")

    threading.Thread(target=_loop, daemon=True).start()
    logger.info(f"Auto-research every {interval_min} min.")


def _start_morning_briefing():
    """Send daily briefing at MORNING_BRIEFING_HOUR (0 = disabled)."""
    hour = int(os.getenv("MORNING_BRIEFING_HOUR", "0"))
    if hour <= 0:
        return
    import threading, time
    from datetime import datetime

    def _loop():
        last_sent_date = None
        while True:
            now = datetime.now()
            if now.hour == hour and last_sent_date != now.date():
                last_sent_date = now.date()
                try:
                    from core.trends import generate_briefing
                    briefing = generate_briefing()
                    _sync_notify(f"☀️ Morning briefing — {now.strftime('%Y-%m-%d')}\n\n{briefing}")
                    logger.info(f"[morning-briefing] sent at {now.strftime('%H:%M')}")
                except Exception as e:
                    from core.error_logger import log_error
                    log_error("morning_briefing", "Failed to generate/send briefing", str(e))
                    logger.error(f"[morning-briefing] {e}")
            time.sleep(600)

    threading.Thread(target=_loop, daemon=True).start()
    logger.info(f"Morning briefing scheduled at {hour:02d}:00.")


def _start_background_services():
    """Start reminder watcher, autonomous agent, and backup scheduler."""
    _start_auto_research()
    _start_morning_briefing()

    # Backup scheduler — checks every 1h, backs up every 24h
    from core.backup import start_backup_scheduler
    start_backup_scheduler()

    # Reminder watcher — notifies via Telegram
    from core.reminders import start_watcher
    from datetime import datetime

    def _on_reminder_due(r):
        dt_str = r.get("dt", "")
        try:
            dt_str = datetime.fromisoformat(dt_str).strftime("%H:%M")
        except Exception:
            pass
        _sync_notify(f"⏰ *Reminder [{dt_str}]:* {r['title']}")

    start_watcher(on_due=_on_reminder_due)
    logger.info("Reminder watcher started.")

    # Autonomous agent (collect + smart alert + daily ideas)
    from core.agent import start_autonomous_agent, set_notify
    set_notify(_sync_notify)

    from core.intel import collect_and_index
    start_autonomous_agent(collect_fn=collect_and_index)
    logger.info("Autonomous agent started.")


# ── Main ───────────────────────────────────────────────────────────────────────

async def _post_init(app: Application):
    """Register bot commands with Telegram (shows in the / menu)."""
    commands = [
        BotCommand("research",  "Collect HN + Reddit + GitHub + summary"),
        BotCommand("briefing",  "World briefing + segment map (/briefing 14)"),
        BotCommand("predict",   "Cross-niche predictions with probabilities (/predict 14)"),
        BotCommand("flows",     "Money flows: sectors where money is moving now (/flows 14)"),
        BotCommand("ideas",     "5 business ideas based on trends"),
        BotCommand("market",    "Crypto + stocks + forex snapshot"),
        BotCommand("news",      "Latest news items (/news 20)"),
        BotCommand("ask",       "RAG search (/ask your question)"),
        BotCommand("tokens",    "Anthropic token usage and cost"),
        BotCommand("set",       "Settings (/set lang EN)"),
        BotCommand("logs",      "Recent error log"),
        BotCommand("stats",     "Knowledge base statistics"),
        BotCommand("reports",   "Saved reports"),
        BotCommand("report",    "Generate report on a topic"),
        BotCommand("rss",       "Manage RSS feeds (/rss list | add | remove)"),
        BotCommand("remind",    "Add reminder"),
        BotCommand("reminders", "List active reminders"),
        BotCommand("start",     "Show menu"),
    ]
    await app.bot.set_my_commands(commands)
    logger.info("Bot commands registered.")


def main():
    if not BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not set in .env")
        sys.exit(1)

    if not ALLOWED_UIDS:
        print("⚠️  TELEGRAM_ALLOWED_USER_ID not set — bot will respond to everyone!")
    else:
        print(f"✅ Allowed users: {ALLOWED_UIDS}")

    global _bot_app
    app = Application.builder().token(BOT_TOKEN).post_init(_post_init).build()
    _bot_app = app

    # Register handlers
    app.add_handler(CommandHandler("start",     handle_start))
    app.add_handler(CommandHandler("research",  handle_research))
    app.add_handler(CommandHandler("ask",       handle_ask))
    app.add_handler(CommandHandler("ideas",     handle_ideas))
    app.add_handler(CommandHandler("market",    handle_market))
    app.add_handler(CommandHandler("briefing",  handle_briefing))
    app.add_handler(CommandHandler("predict",   handle_predict))
    app.add_handler(CommandHandler("flows",     handle_flows))
    app.add_handler(CommandHandler("remind",    handle_remind))
    app.add_handler(CommandHandler("reminders", handle_reminders))
    app.add_handler(CommandHandler("news",      handle_news))
    app.add_handler(CommandHandler("stats",     handle_stats))
    app.add_handler(CommandHandler("reports",   handle_reports))
    app.add_handler(CommandHandler("report",    handle_report))
    app.add_handler(CommandHandler("tokens",    handle_tokens))
    app.add_handler(CommandHandler("logs",      handle_logs))
    app.add_handler(CommandHandler("set",       handle_set))
    app.add_handler(CommandHandler("rss",       handle_rss))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Start background threads after bot is initialized
    _start_background_services()

    logger.info("Bot started. Listening for updates...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
