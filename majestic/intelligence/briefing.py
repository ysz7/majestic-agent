"""Briefing persistence — load the most recent saved briefing."""

from __future__ import annotations


def load_recent_briefing(settings, max_days: int = 3) -> str | None:
    """Return the most recent saved briefing within *max_days* days, or None."""
    from datetime import date as _d, timedelta as _td
    try:
        bd = settings.workspace_dir / "briefings"
        if not bd.exists():
            return None
        today = _d.today()
        for delta in range(max_days + 1):
            f = bd / f"{(today - _td(days=delta)).isoformat()}.md"
            if f.exists():
                content = f.read_text(encoding="utf-8")
                if content.strip():
                    return content
    except Exception:
        pass
    return None
