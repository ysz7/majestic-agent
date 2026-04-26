"""
Token usage tracker — persisted to MAJESTIC_HOME/tokens.json.

Pricing defaults (Claude Sonnet 4):
  INPUT  = $3.00  per 1M tokens
  OUTPUT = $15.00 per 1M tokens
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from threading import Lock

from majestic.constants import MAJESTIC_HOME

_PATH = MAJESTIC_HOME / "tokens.json"
_lock = Lock()

INPUT_PRICE_PER_M  = 3.00
OUTPUT_PRICE_PER_M = 15.00

_DEFAULTS: dict = {
    "tokens_in": 0, "tokens_out": 0, "requests": 0,
    "cache_write": 0, "cache_read": 0,
    "cost_usd": 0.0, "reset_date": "", "history": [],
}


def _load() -> dict:
    if _PATH.exists():
        try:
            return {**_DEFAULTS, **json.loads(_PATH.read_text(encoding="utf-8"))}
        except Exception:
            pass
    d = dict(_DEFAULTS)
    d["reset_date"] = datetime.now().strftime("%Y-%m-%d")
    return d


def _save(d: dict) -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")


def track(
    tokens_in: int,
    tokens_out: int,
    operation: str = "query",
    cache_write: int = 0,
    cache_read: int = 0,
    cost_override: float | None = None,
) -> None:
    if cost_override is not None:
        cost = cost_override
    else:
        cost = (tokens_in / 1_000_000 * INPUT_PRICE_PER_M) + (tokens_out / 1_000_000 * OUTPUT_PRICE_PER_M)
        # Cache write costs 1.25x input, cache read costs 0.10x input
        cost += (cache_write / 1_000_000 * INPUT_PRICE_PER_M * 1.25)
        cost += (cache_read  / 1_000_000 * INPUT_PRICE_PER_M * 0.10)
    with _lock:
        d = _load()
        d.setdefault("reset_date", datetime.now().strftime("%Y-%m-%d"))
        d["tokens_in"]   += tokens_in
        d["tokens_out"]  += tokens_out
        d["cache_write"] = d.get("cache_write", 0) + cache_write
        d["cache_read"]  = d.get("cache_read",  0) + cache_read
        d["requests"]    += 1
        d["cost_usd"]     = round(d["cost_usd"] + cost, 6)
        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "operation": operation,
            "in": tokens_in, "out": tokens_out,
            "cache_write": cache_write, "cache_read": cache_read,
            "cost": round(cost, 6),
        }
        d["history"] = ([entry] + d.get("history", []))[:30]
        _save(d)


def track_response(response: object, operation: str = "query") -> None:
    if os.getenv("LLM_PROVIDER", "").lower() == "ollama":
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


def reset_stats() -> None:
    d = dict(_DEFAULTS)
    d["reset_date"] = datetime.now().strftime("%Y-%m-%d")
    _save(d)


def format_stats() -> str:
    d = get_stats()
    today = datetime.now().date()
    cost_today = sum(
        e.get("cost", 0.0) for e in d.get("history", [])
        if _is_today(e.get("ts", ""), today)
    )
    tin    = d.get("tokens_in", 0)
    tout   = d.get("tokens_out", 0)
    cwrite = d.get("cache_write", 0)
    cread  = d.get("cache_read",  0)
    total  = d.get("cost_usd", 0.0)

    # What cread would have cost at full price vs cached price
    saved  = cread / 1_000_000 * INPUT_PRICE_PER_M * (1 - 0.10) if cread else 0.0

    lines = [
        "📊 Token Usage",
        f"  In:          {tin:>10,}  (${tin  / 1_000_000 * INPUT_PRICE_PER_M:.4f})",
        f"  Out:         {tout:>10,}  (${tout / 1_000_000 * OUTPUT_PRICE_PER_M:.4f})",
    ]
    if cwrite or cread:
        lines += [
            f"  Cache write: {cwrite:>10,}  (${cwrite / 1_000_000 * INPUT_PRICE_PER_M * 1.25:.4f})",
            f"  Cache read:  {cread:>10,}  (${cread  / 1_000_000 * INPUT_PRICE_PER_M * 0.10:.4f})",
            f"  Saved:                   ~${saved:.4f} via cache",
        ]
    lines += [
        f"  Total: ${total:.4f}",
        f"  Today: ${cost_today:.4f}",
        f"  Since: {d.get('reset_date', '—')}",
    ]
    return "\n".join(lines)


def _is_today(ts: str, today: object) -> bool:
    try:
        return datetime.fromisoformat(ts).date() == today
    except Exception:
        return False
