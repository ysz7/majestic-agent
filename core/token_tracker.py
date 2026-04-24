"""
Anthropic token usage tracker.
Persisted to data/tokens.json.

Pricing (Claude Sonnet 4):
  INPUT  = $3.00  per 1M tokens
  OUTPUT = $15.00 per 1M tokens

Usage:
  from core.token_tracker import track_response, format_stats, reset
  track_response(llm_response, "briefing")   # call after every llm.invoke()
"""
import json
import os
from datetime import datetime
from pathlib import Path
from threading import Lock

_DATA_PATH = Path(__file__).parent.parent / "data" / "tokens.json"
_lock = Lock()

INPUT_PRICE_PER_M  = 3.00    # USD per 1M input tokens
OUTPUT_PRICE_PER_M = 15.00   # USD per 1M output tokens

_DEFAULTS: dict = {
    "tokens_in":  0,
    "tokens_out": 0,
    "requests":   0,
    "cost_usd":   0.0,
    "reset_date": "",
    "history":    [],
}


def _load() -> dict:
    if _DATA_PATH.exists():
        try:
            return {**_DEFAULTS, **json.loads(_DATA_PATH.read_text(encoding="utf-8"))}
        except Exception:
            pass
    d = dict(_DEFAULTS)
    d["reset_date"] = datetime.now().strftime("%Y-%m-%d")
    return d


def _save(d: dict):
    _DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    _DATA_PATH.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")


def track(tokens_in: int, tokens_out: int, operation: str = "query"):
    """Record a single Anthropic LLM call."""
    cost = (tokens_in / 1_000_000 * INPUT_PRICE_PER_M) + (tokens_out / 1_000_000 * OUTPUT_PRICE_PER_M)
    with _lock:
        d = _load()
        if not d.get("reset_date"):
            d["reset_date"] = datetime.now().strftime("%Y-%m-%d")
        d["tokens_in"]  += tokens_in
        d["tokens_out"] += tokens_out
        d["requests"]   += 1
        d["cost_usd"]    = round(d["cost_usd"] + cost, 6)
        entry = {
            "ts":        datetime.now().isoformat(timespec="seconds"),
            "operation": operation,
            "in":        tokens_in,
            "out":       tokens_out,
            "cost":      round(cost, 6),
        }
        d["history"] = ([entry] + d.get("history", []))[:30]
        _save(d)


def track_response(response, operation: str = "query"):
    """Extract usage from an LLM response and call track(). No-op for free/local providers."""
    if os.getenv("LLM_PROVIDER", "ollama").lower() == "ollama":
        return
    try:
        um = getattr(response, "usage_metadata", None) or {}
        tin  = um.get("input_tokens", 0) or 0
        tout = um.get("output_tokens", 0) or 0
        if tin or tout:
            track(tin, tout, operation)
    except Exception:
        pass


def get_stats() -> dict:
    return _load()


def reset():
    """Clear all counters and history."""
    d = dict(_DEFAULTS)
    d["reset_date"] = datetime.now().strftime("%Y-%m-%d")
    _save(d)


def format_stats() -> str:
    """Return a formatted usage summary string for CLI/Telegram display."""
    d = get_stats()
    today = datetime.now().date()

    cost_today = 0.0
    for e in d.get("history", []):
        try:
            if datetime.fromisoformat(e["ts"]).date() == today:
                cost_today += e.get("cost", 0.0)
        except Exception:
            pass

    tokens_in  = d.get("tokens_in", 0)
    tokens_out = d.get("tokens_out", 0)
    requests   = d.get("requests", 0)
    total_cost = d.get("cost_usd", 0.0)
    reset_date = d.get("reset_date", "—")

    input_cost  = tokens_in  / 1_000_000 * INPUT_PRICE_PER_M
    output_cost = tokens_out / 1_000_000 * OUTPUT_PRICE_PER_M

    lines = [
        "📊 Anthropic Usage",
        "",
        f"  Tokens in:    {tokens_in:>13,}",
        f"  Tokens out:   {tokens_out:>13,}",
        f"  Requests:     {requests:>13,}",
        "",
        "  Cost:",
        f"    Input:      ${input_cost:>9.2f}",
        f"    Output:     ${output_cost:>9.2f}",
        f"    Total:      ${total_cost:>9.2f}  💰",
        "",
        f"  Today:        ${cost_today:>9.2f}",
        f"  Since reset:  ${total_cost:>9.2f}",
        f"  Reset date:   {reset_date}",
    ]

    history = d.get("history", [])[:5]
    if history:
        lines.append("")
        lines.append("  Recent operations:")
        for e in reversed(history):
            try:
                ts = datetime.fromisoformat(e["ts"])
                date_label = "today" if ts.date() == today else ts.strftime("%m-%d")
                time_label = ts.strftime("%H:%M")
            except Exception:
                date_label, time_label = "", ""
            op   = e.get("operation", "?")[:18]
            cost = e.get("cost", 0.0)
            lines.append(f"  • {op:<18} — ${cost:.4f}  ({date_label} {time_label})")

    return "\n".join(lines)
