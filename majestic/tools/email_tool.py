"""Send email tool — uses configured SMTP settings from config."""
from __future__ import annotations

from majestic.tools.registry import tool


@tool(
    name="send_email",
    description=(
        "Send an email using the configured SMTP settings. "
        "Use when the user asks to send a report, summary, or notification by email. "
        "Requires email to be configured in settings (smtp_host, username, password)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "Recipient email address",
            },
            "subject": {
                "type": "string",
                "description": "Email subject line",
            },
            "body": {
                "type": "string",
                "description": "Email body — plain text or Markdown",
            },
        },
        "required": ["to", "subject", "body"],
    },
)
def send_email(to: str, subject: str, body: str) -> str:
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    from majestic import config as cfg

    ec = cfg.get("email") or {}
    username = ec.get("username") or cfg.get("email.username") or ""
    password = ec.get("password") or cfg.get("email.password") or ""
    smtp_host = ec.get("smtp_host", "smtp.gmail.com")
    smtp_port = int(ec.get("smtp_port", 587))

    if not username or not password:
        return (
            "Email not configured. Set email.username, email.password, "
            "and email.smtp_host in config."
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = username
    msg["To"] = to

    msg.attach(MIMEText(body, "plain", "utf-8"))

    # Try to convert markdown to HTML
    try:
        import markdown
        html_body = markdown.markdown(body)
        msg.attach(MIMEText(html_body, "html", "utf-8"))
    except ImportError:
        pass

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(username, password)
            smtp.sendmail(username, to, msg.as_string())
        return f"Email sent to {to}: {subject!r}"
    except Exception as e:
        return f"[email error] {e}"
