"""Get current date and time in various formats and timezones."""
from __future__ import annotations

from majestic.tools.registry import tool


@tool(
    name="get_datetime",
    description=(
        "Get the current date and time. "
        "Use when you need to know the exact current time, create timestamps, "
        "calculate deadlines, or reference today's date in reports."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "timezone": {
                "type": "string",
                "description": "Timezone name, e.g. 'UTC', 'Europe/Kyiv', 'US/Eastern' (default: UTC)",
            },
            "format": {
                "type": "string",
                "description": "Output format: 'iso', 'human', 'date', 'time', 'unix' (default: human)",
            },
        },
    },
)
def get_datetime(timezone: str = "UTC", format: str = "human") -> str:
    from datetime import datetime, timezone as _tz
    import time

    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(timezone)
        now = datetime.now(tz)
    except Exception:
        now = datetime.now(_tz.utc)
        timezone = "UTC"

    if format == "iso":
        return now.isoformat()
    if format == "date":
        return now.strftime("%Y-%m-%d")
    if format == "time":
        return now.strftime("%H:%M:%S")
    if format == "unix":
        return str(int(now.timestamp()))
    # human (default)
    return now.strftime(f"%A, %B %d %Y, %H:%M:%S {timezone}")
