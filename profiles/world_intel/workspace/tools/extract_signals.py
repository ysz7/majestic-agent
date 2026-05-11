"""
extract_signals.py — Extract structured investment signals from collected news.

Usage:
    python extract_signals.py today
    python extract_signals.py --date 2026-05-11
    python extract_signals.py --news_id <id>
"""

import sys
import json
import subprocess
import argparse
import re
import httpx
from pathlib import Path
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_TOOLS_DIR = Path(__file__).parent
_PROFILE_ROOT = Path(__file__).parents[2]   # = profiles/world_intel/
_PROJECT_ROOT = Path(__file__).parents[4]   # = c:/ysz/DEV/majestic-agent/
_DATA_DIR = _PROFILE_ROOT / "data"
_OUTPUT_DIR = _PROFILE_ROOT / "workspace" / "output"

# ---------------------------------------------------------------------------
# Env / LLM helpers
# ---------------------------------------------------------------------------


def _load_env() -> dict:
    env = {}
    for path in [_PROJECT_ROOT / ".env", _PROFILE_ROOT / ".env"]:
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()  # later file overrides earlier
    return env


def _call_llm(prompt: str, system: str, env: dict, max_tokens: int = 1500) -> str:
    api_key = env.get("OPENROUTER_API_KEY") or env.get("ANTHROPIC_API_KEY") or env.get("OPENAI_API_KEY")
    ollama_url = env.get("OLLAMA_BASE_URL")
    if not api_key and not ollama_url:
        return ""
    if ollama_url and not api_key:
        url = f"{ollama_url.rstrip('/')}/v1/chat/completions"
        model = env.get("OLLAMA_MODEL", "llama3.2")
        headers = {"Content-Type": "application/json"}
    else:
        url = "https://openrouter.ai/api/v1/chat/completions"
        model = env.get("MAJESTIC_MODEL_REASON", "anthropic/claude-sonnet-4-5")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/majestic-agent",
            "X-Title": "Majestic World Intel Agent",
        }
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    try:
        resp = httpx.post(url, headers=headers, json=body, timeout=120)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        return f"[LLM error: {exc}]"


# ---------------------------------------------------------------------------
# JSON parsing safety
# ---------------------------------------------------------------------------


def _parse_json_safe(text: str) -> list:
    try:
        # Try direct parse
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON array from text
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
    return []


# ---------------------------------------------------------------------------
# DB subprocess helpers
# ---------------------------------------------------------------------------


def _get_news_by_date(date: str) -> list[dict]:
    """Load news items for a given date via db_news.py get_by_date."""
    result = subprocess.run(
        [sys.executable, str(_TOOLS_DIR / "db_news.py"), "get_by_date", date],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode == 0 and result.stdout.strip():
        try:
            return json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            return []
    if result.stderr.strip():
        print(f"[extract_signals] db_news.py get_by_date error: {result.stderr.strip()}", file=sys.stderr)
    return []


def _get_news_by_id(news_id: int) -> list[dict]:
    """Load a single news item by ID via db_news.py get."""
    result = subprocess.run(
        [sys.executable, str(_TOOLS_DIR / "db_news.py"), "get", str(news_id)],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode == 0 and result.stdout.strip():
        try:
            data = json.loads(result.stdout.strip())
            # db_news.py get may return a single object or a list
            if isinstance(data, list):
                return data
            return [data]
        except json.JSONDecodeError:
            return []
    if result.stderr.strip():
        print(f"[extract_signals] db_news.py get error: {result.stderr.strip()}", file=sys.stderr)
    return []


def _save_signal(payload: dict) -> dict:
    """Save a signal to the DB via db_signals.py save."""
    payload_str = json.dumps(payload, ensure_ascii=False)
    try:
        result = subprocess.run(
            [sys.executable, str(_TOOLS_DIR / "db_signals.py"), "save", payload_str],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout.strip())
        print(f"[extract_signals] db_signals.py save error: {result.stderr.strip()}", file=sys.stderr)
        return {}
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f"[extract_signals] db_signals.py save exception: {exc}", file=sys.stderr)
        return {}


# ---------------------------------------------------------------------------
# Signal extraction prompt
# ---------------------------------------------------------------------------

_SIGNAL_SYSTEM = "You are a financial analyst extracting structured investment signals from news. Return valid JSON only."

_SIGNAL_USER_TEMPLATE = """\
Extract investment signals from this news item.

Headline: {headline}
Summary: {summary}
Category: {category}

Return a JSON array of signals found. Each signal must have a 'type' field.

Types and required fields:
- funding_round: {{type, company, amount_usd_millions, stage, investors, sector, niche, country, significance}}
  significance: "low"|"medium"|"high"|"landmark"
- policy_change: {{type, region, direction, affected_niches, urgency, description}}
  direction: "enables"|"restricts"|"incentivizes"
  urgency: "immediate"|"6_months"|"1_year_plus"
- market_move: {{type, asset, direction, magnitude_pct, context}}
  direction: "up"|"down"

If no clear signal, return [].
Return ONLY the JSON array, no explanation."""


def _extract_signals_from_news(item: dict, env: dict) -> list[dict]:
    """Call LLM to extract signals from one news item. Returns a list of signal dicts."""
    headline = item.get("headline", "")
    summary = item.get("summary", "")
    category = item.get("category", "")

    if not headline and not summary:
        return []

    prompt = _SIGNAL_USER_TEMPLATE.format(
        headline=headline,
        summary=summary,
        category=category,
    )
    raw = _call_llm(prompt, _SIGNAL_SYSTEM, env, max_tokens=1500)

    if not raw or raw.startswith("[LLM error"):
        print(f"[extract_signals] LLM returned error/empty for news_id={item.get('id')}", file=sys.stderr)
        return []

    signals = _parse_json_safe(raw)
    if not isinstance(signals, list):
        return []
    return signals


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------


def _process_items(items: list[dict], env: dict) -> dict:
    processed = 0
    signals_extracted = 0
    by_type: dict[str, int] = {}

    for item in items:
        news_id = item.get("id")
        print(
            f"[extract_signals] processing news_id={news_id}: {item.get('headline', '')[:80]}",
            file=sys.stderr,
        )

        signals = _extract_signals_from_news(item, env)
        processed += 1

        for signal in signals:
            sig_type = signal.get("type", "unknown")
            # Attach the originating news_id for traceability
            signal["news_id"] = news_id

            saved = _save_signal(signal)
            if saved:
                signals_extracted += 1
                by_type[sig_type] = by_type.get(sig_type, 0) + 1
                print(
                    f"[extract_signals] saved signal type={sig_type} from news_id={news_id}",
                    file=sys.stderr,
                )

    return {
        "processed": processed,
        "signals_extracted": signals_extracted,
        "by_type": by_type,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract structured investment signals from collected news."
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "today_keyword",
        nargs="?",
        metavar="today",
        help="Pass 'today' to process today's news.",
    )
    group.add_argument(
        "--date",
        help="Process news collected on this date (YYYY-MM-DD).",
    )
    group.add_argument(
        "--news_id",
        type=int,
        help="Process a single news item by its DB id.",
    )

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    env = _load_env()

    # Determine which news items to load
    if args.news_id is not None:
        items = _get_news_by_id(args.news_id)
    elif args.date:
        items = _get_news_by_date(args.date)
    elif args.today_keyword and args.today_keyword.lower() == "today":
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        items = _get_news_by_date(date_str)
    else:
        # Default: today
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        items = _get_news_by_date(date_str)

    if not items:
        result = {
            "processed": 0,
            "signals_extracted": 0,
            "by_type": {},
            "note": "No news items found for the given criteria.",
        }
        print(json.dumps(result, indent=2))
        return

    result = _process_items(items, env)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
