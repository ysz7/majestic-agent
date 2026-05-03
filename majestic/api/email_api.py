"""Email gateway management API handlers."""
from __future__ import annotations

import threading
import time
from typing import Any

_state: dict[str, Any] = {
    "running": False,
    "thread": None,
    "last_poll": None,
    "error": None,
    "stop_event": None,
}


def handle_email_status() -> dict:
    from majestic import config as cfg
    ec = cfg.get("email") or {}
    configured = bool(ec.get("username") and ec.get("password"))
    return {
        "configured": configured,
        "running": _state["running"],
        "last_poll": _state["last_poll"],
        "error": _state["error"],
        "username": ec.get("username", ""),
    }


def handle_email_test(body: dict) -> dict:
    import imaplib
    imap_host = body.get("imap_host", "imap.gmail.com")
    imap_port = int(body.get("imap_port", 993))
    username  = body.get("username", "")
    password  = body.get("password", "")
    if not username or not password:
        return {"ok": False, "error": "username and password are required"}
    try:
        with imaplib.IMAP4_SSL(imap_host, imap_port, timeout=10) as imap:
            imap.login(username, password)
            imap.select("INBOX")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def handle_email_save(body: dict) -> dict:
    from majestic import config as cfg
    fields = [
        "imap_host", "imap_port", "smtp_host", "smtp_port",
        "username", "password", "poll_interval", "allowed_senders",
    ]
    ec = dict(cfg.get("email") or {})
    for f in fields:
        if f in body:
            ec[f] = body[f]
    cfg.set_value("email", ec)
    return {"ok": True}


def handle_email_start(body: dict) -> dict:
    if _state["running"]:
        return {"ok": True, "message": "already running"}

    # Save config from body if provided
    if body:
        handle_email_save(body)

    from majestic import config as cfg
    ec = cfg.get("email") or {}
    if not ec.get("username") or not ec.get("password"):
        return {"ok": False, "error": "Email not configured. Set username and password first."}

    stop_event = threading.Event()
    _state["stop_event"] = stop_event
    _state["error"] = None

    def _run() -> None:
        _state["running"] = True
        interval = int((cfg.get("email") or {}).get("poll_interval", 60))
        from majestic.gateway.email_gw import EmailPlatform
        platform = EmailPlatform()
        while not stop_event.is_set():
            try:
                ec_now = cfg.get("email") or {}
                platform._poll_once(ec_now)
                _state["last_poll"] = time.time()
                _state["error"] = None
            except Exception as e:
                _state["error"] = str(e)
            stop_event.wait(timeout=interval)
        _state["running"] = False

    t = threading.Thread(target=_run, daemon=True, name="email-gateway")
    _state["thread"] = t
    t.start()
    return {"ok": True, "message": "started"}


def handle_email_stop() -> dict:
    ev = _state.get("stop_event")
    if ev:
        ev.set()
    _state["running"] = False
    return {"ok": True, "message": "stopped"}
