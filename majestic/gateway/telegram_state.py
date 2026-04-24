"""
Shared state, helpers, and concurrency gate for the Telegram gateway.

Imported by both telegram.py (Platform class) and telegram_handlers.py (handlers).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

TG_MAX = 4096
_SESSION_MAX = 10

# Per-user in-memory history and DB session IDs
_history:     dict[int, list[tuple[str, str]]] = {}
_db_sessions: dict[int, str] = {}

# Telegram Application reference (set in TelegramPlatform.start)
_app = None


# ── Text helpers ──────────────────────────────────────────────────────────────

def _split_text(text: str, max_len: int = TG_MAX) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
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


# ── Session management ────────────────────────────────────────────────────────

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


# ── Push notification (called from non-async threads) ─────────────────────────

def _sync_notify(text: str) -> None:
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


# ── Access control ────────────────────────────────────────────────────────────

def _allowed(update) -> bool:
    from majestic.config import get as cfg_get
    allowed = cfg_get("telegram.allowed_user_ids") or []
    return (not allowed) or (update.effective_user and update.effective_user.id in set(allowed))


async def _deny(update) -> None:
    await update.message.reply_text("⛔ Access denied.")


# ── Concurrency gate ──────────────────────────────────────────────────────────

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
