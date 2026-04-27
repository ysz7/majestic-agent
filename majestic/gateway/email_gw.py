"""
Email gateway — IMAP polling + SMTP replies.

Config in config.yaml:
  email:
    imap_host: imap.gmail.com
    smtp_host: smtp.gmail.com
    imap_port: 993
    smtp_port: 587
    username: user@gmail.com
    password: app-password
    poll_interval: 60
    allowed_senders: []   # empty = allow all

Start: majestic gateway start email
"""
from __future__ import annotations

import asyncio
import email as _email
import imaplib
import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from .base import Platform


class EmailPlatform(Platform):
    name = "email"

    def is_configured(self) -> bool:
        from majestic import config as cfg
        ec = cfg.get("email") or {}
        return bool(ec.get("username") and ec.get("password"))

    async def start(self) -> None:
        from majestic import config as cfg
        ec = cfg.get("email") or {}
        interval = int(ec.get("poll_interval", 60))
        print(f"  Email gateway polling every {interval}s as {ec.get('username')}")
        loop = asyncio.get_event_loop()
        while True:
            try:
                await loop.run_in_executor(None, self._poll_once, ec)
            except Exception as e:
                print(f"  [email] poll error: {e}")
            await asyncio.sleep(interval)

    def _poll_once(self, ec: dict) -> None:
        imap_host = ec.get("imap_host", "imap.gmail.com")
        imap_port = int(ec.get("imap_port", 993))
        username  = ec.get("username", "")
        password  = ec.get("password", "")
        allowed   = [s.lower().strip() for s in (ec.get("allowed_senders") or [])]

        with imaplib.IMAP4_SSL(imap_host, imap_port) as imap:
            imap.login(username, password)
            imap.select("INBOX")
            _, data = imap.search(None, "UNSEEN")
            ids = data[0].split() if data[0] else []
            for uid in ids:
                try:
                    _, msg_data = imap.fetch(uid, "(RFC822)")
                    raw = msg_data[0][1]
                    msg = _email.message_from_bytes(raw)
                    sender  = _parse_addr(msg.get("From", ""))
                    subject = msg.get("Subject", "").strip()
                    body    = _get_text_body(msg).strip()
                    user_msg = subject or body
                    if not user_msg:
                        continue
                    if allowed and sender.lower() not in allowed:
                        continue
                    reply = self._run_agent(user_msg)
                    self._send_reply(ec, sender, subject, reply)
                    imap.store(uid, "+FLAGS", "\\Seen")
                except Exception as e:
                    print(f"  [email] message error: {e}")

    def _run_agent(self, message: str) -> str:
        try:
            from majestic.agent.loop import AgentLoop
            result = AgentLoop().run(message)
            return result.get("answer", "No response.")
        except Exception as e:
            return f"Agent error: {e}"

    def _send_reply(self, ec: dict, to: str, subject: str, body: str) -> None:
        smtp_host = ec.get("smtp_host", "smtp.gmail.com")
        smtp_port = int(ec.get("smtp_port", 587))
        username  = ec.get("username", "")
        password  = ec.get("password", "")

        reply_subject = f"Re: {subject}" if not subject.startswith("Re:") else subject
        msg = MIMEMultipart("alternative")
        msg["From"]    = username
        msg["To"]      = to
        msg["Subject"] = reply_subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(smtp_host, smtp_port) as smtp:
            smtp.starttls()
            smtp.login(username, password)
            smtp.sendmail(username, to, msg.as_string())


def _parse_addr(raw: str) -> str:
    import re
    m = re.search(r"<([^>]+)>", raw)
    return m.group(1) if m else raw.strip()


def _get_text_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                except Exception:
                    pass
    else:
        try:
            return msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", errors="replace"
            )
        except Exception:
            pass
    return ""
