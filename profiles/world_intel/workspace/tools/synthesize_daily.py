"""
synthesize_daily.py — Generate full daily intelligence brief.

Usage:
    python synthesize_daily.py
    python synthesize_daily.py --date 2026-05-11
"""

import json
import sys
import subprocess
import argparse
from datetime import datetime, timezone
from pathlib import Path

_PROFILE_ROOT = Path(__file__).parents[2]  # = profiles/world_intel/
_PROJECT_ROOT = Path(__file__).parents[4]  # = c:/ysz/DEV/majestic-agent/
_DATA_DIR = _PROFILE_ROOT / "data"
_OUTPUT_DIR = _PROFILE_ROOT / "workspace" / "output"
_TOOLS_DIR = Path(__file__).parent

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
                    env[k.strip()] = v.strip()
    return env


def _call_llm(prompt: str, system: str, env: dict, max_tokens: int = 2000) -> str:
    import httpx
    api_key = env.get("OPENROUTER_API_KEY") or env.get("ANTHROPIC_API_KEY") or env.get("OPENAI_API_KEY")
    ollama_url = env.get("OLLAMA_BASE_URL")
    if not api_key and not ollama_url:
        return "[LLM unavailable]"
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
        "temperature": 0.3,
    }
    try:
        resp = httpx.post(url, headers=headers, json=body, timeout=120)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        return f"[LLM error: {exc}]"


# ---------------------------------------------------------------------------
# Subprocess helper
# ---------------------------------------------------------------------------

def _run_tool(tool_name: str, *args) -> dict | list:
    result = subprocess.run(
        [sys.executable, str(_TOOLS_DIR / tool_name), *args],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode == 0 and result.stdout.strip():
        try:
            return json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            return {}
    return {}


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _bar(amount: float, max_amount: float, width: int = 20) -> str:
    """Return a bar of █ characters proportional to amount."""
    if max_amount <= 0:
        return ""
    filled = int(round(amount / max_amount * width))
    return "█" * filled


def _format_funding_line(data: dict) -> str:
    amount = data.get("amount_usd_millions") or data.get("amount_millions") or data.get("amount", 0)
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        amount = 0.0
    stage = data.get("stage") or data.get("series") or data.get("round") or ""
    company = data.get("company") or data.get("name") or ""
    niche = data.get("niche") or data.get("sector") or ""
    investors = data.get("investors") or data.get("lead_investor") or ""
    return f"  ${amount:.1f}M  {stage}  {company}  {niche}  {investors}".strip()


def _classify_news_category(item: dict) -> str:
    cat = (item.get("category") or "").lower()
    if cat in ("technology", "tech", "ai", "software"):
        return "TECHNOLOGY"
    if cat in ("funding", "venture", "investment"):
        return "FUNDING"
    if cat in ("macro", "markets", "economy", "finance"):
        return "MACRO AND MARKETS"
    if cat in ("policy", "regulation", "legal", "government"):
        return "POLICY AND REGULATION"
    if cat in ("geopolitics", "politics", "international", "war"):
        return "GEOPOLITICS"
    return "TECHNOLOGY"


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def synthesize(date: str) -> dict:
    env = _load_env()

    # 1. Load top-10 news by importance
    all_news_raw = _run_tool("db_news.py", "get_by_date", date)
    if not isinstance(all_news_raw, list):
        all_news_raw = []
    # Also try --limit 20 variant (db_news get_by_date doesn't take limit but get_by_category does)
    all_news_raw_limited = all_news_raw[:20]
    top_news = sorted(all_news_raw_limited, key=lambda x: int(x.get("importance", 3)), reverse=True)[:10]

    # 2. Load funding signals
    funding_signals_raw = _run_tool("db_signals.py", "get_funding_signals", "--date", date)
    if not isinstance(funding_signals_raw, list):
        funding_signals_raw = []

    # 3. Load policy signals
    policy_signals_raw = _run_tool("db_signals.py", "get_policy_signals", "--date", date)
    if not isinstance(policy_signals_raw, list):
        policy_signals_raw = []

    # 4. Load market_move signals
    market_signals_raw = _run_tool("db_signals.py", "get_by_type", "market_move", "--date", date)
    if not isinstance(market_signals_raw, list):
        market_signals_raw = []

    # 5. Load flow data
    flows_raw = _run_tool("db_flows.py", "get_by_period", date)
    if not isinstance(flows_raw, list):
        flows_raw = []

    # --- Parse funding signal data ---
    funding_parsed = []
    total_funding = 0.0
    for sig in funding_signals_raw:
        try:
            data = json.loads(sig.get("data_json", "{}"))
        except (json.JSONDecodeError, AttributeError):
            data = {}
        amount = 0.0
        for field in ("amount_usd_millions", "amount_millions", "amount"):
            val = data.get(field)
            if val is not None:
                try:
                    amount = float(val)
                    break
                except (TypeError, ValueError):
                    pass
        total_funding += amount
        funding_parsed.append((amount, data))
    funding_parsed.sort(key=lambda x: x[0], reverse=True)

    # --- LLM: Signal analysis narrative ---
    funding_summary_for_llm = "\n".join(
        f"- {d.get('company', 'Unknown')}: ${a:.1f}M ({d.get('stage', '')} | {d.get('niche', '')})"
        for a, d in funding_parsed[:15]
    )
    policy_summary_for_llm = "\n".join(
        sig.get("data_json", "{}") for sig in policy_signals_raw[:10]
    )

    signal_narrative = _call_llm(
        prompt=(
            f"Funding signals for {date}:\n{funding_summary_for_llm}\n\n"
            f"Policy signals:\n{policy_summary_for_llm}"
        ),
        system=(
            "Given these funding signals and policy changes, write 3-4 sentences about what these events mean "
            "together for capital flows and investment themes. Be specific. Cite amounts. No generic phrases."
        ),
        env=env,
        max_tokens=500,
    )

    # --- LLM: Niches to watch ---
    niches_narrative = _call_llm(
        prompt=f"Funding signals for {date}:\n{funding_summary_for_llm}",
        system=(
            "From these funding signals, identify the 3 most notable investment niches showing unusual activity. "
            "For each: Why now? Who is investing? What's the opportunity size? Write 3-4 sentences per niche."
        ),
        env=env,
        max_tokens=700,
    )

    # --- Format sections ---

    # Top 10 news
    news_section_lines = []
    for i, item in enumerate(top_news, 1):
        headline = item.get("headline", "")
        summary = item.get("summary", "")
        source = item.get("source", "")
        source_url = item.get("source_url", "")
        news_section_lines.append(
            f"{i}. {headline}\n   {summary}\n   [{source}]({source_url})"
        )
    news_section = "\n\n".join(news_section_lines) if news_section_lines else "_No news collected yet._"

    # Funding section
    funding_lines = [_format_funding_line(d) for _, d in funding_parsed]
    funding_section = "\n".join(funding_lines) if funding_lines else "_No funding signals collected yet._"
    funding_footer = f"Total: ${total_funding:.1f}M across {len(funding_signals_raw)} deals"

    # Capital flows bar chart
    max_flow_amount = max((f.get("total_amount", 0) for f in flows_raw), default=0)
    flow_lines = []
    for flow in flows_raw:
        seg = flow.get("segment", "")
        amt = float(flow.get("total_amount", 0))
        bar = _bar(amt, max_flow_amount)
        momentum = flow.get("momentum", "stable")
        flow_lines.append(f"  {seg:<20} {bar}  ${amt:.1f}M  [{momentum}]")
    flows_section = "\n".join(flow_lines) if flow_lines else "_No flow data yet._"

    # Outlier note
    outliers = [f for f in flows_raw if f.get("is_outlier")]
    outlier_note = ""
    if outliers:
        names = ", ".join(f.get("segment", "") for f in outliers)
        outlier_note = f"\n> OUTLIER DETECTED: Single deal dominated volume in: {names}"

    # Policy radar
    policy_bullets = []
    for sig in policy_signals_raw:
        try:
            data = json.loads(sig.get("data_json", "{}"))
        except (json.JSONDecodeError, AttributeError):
            data = {}
        desc = data.get("description") or data.get("title") or data.get("policy") or str(data)
        policy_bullets.append(f"- {desc}")
    policy_section = "\n".join(policy_bullets) if policy_bullets else "_No policy signals collected yet._"

    # Macro pulse
    macro_bullets = []
    for sig in market_signals_raw:
        try:
            data = json.loads(sig.get("data_json", "{}"))
        except (json.JSONDecodeError, AttributeError):
            data = {}
        desc = data.get("description") or data.get("move") or data.get("asset") or str(data)
        macro_bullets.append(f"- {desc}")
    macro_section = "\n".join(macro_bullets) if macro_bullets else "_No market signals collected yet._"

    # --- Build daily report ---
    report_md = f"""# WORLD INTELLIGENCE — Daily Brief {date}

## WHAT HAPPENED TODAY

{news_section}

## FUNDING TODAY

{funding_section}
{funding_footer}

## SIGNAL ANALYSIS

{signal_narrative}

## CAPITAL FLOWS — Last 24 Hours

By segment:
{flows_section}
{outlier_note}

## NICHES TO WATCH

{niches_narrative}

## POLICY RADAR

{policy_section}

## MACRO PULSE

{macro_section}
"""

    # --- Save report ---
    report_dir = _OUTPUT_DIR / "reports" / "daily"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{date}.md"
    report_path.write_text(report_md, encoding="utf-8")

    # --- Build news digest by category ---
    categories = {
        "TECHNOLOGY": [],
        "FUNDING": [],
        "MACRO AND MARKETS": [],
        "POLICY AND REGULATION": [],
        "GEOPOLITICS": [],
    }
    for item in all_news_raw:
        cat_key = _classify_news_category(item)
        headline = item.get("headline", "")
        source = item.get("source", "")
        categories[cat_key].append(f"· {headline} [{source}]")

    digest_sections = [f"# WORLD NEWS — {date}\n"]
    for cat_name, bullets in categories.items():
        digest_sections.append(f"## {cat_name}")
        digest_sections.append("\n".join(bullets) if bullets else "_None_")
        digest_sections.append("")
    digest_md = "\n".join(digest_sections)

    digest_dir = _OUTPUT_DIR / "news"
    digest_dir.mkdir(parents=True, exist_ok=True)
    digest_path = digest_dir / f"{date}.md"
    digest_path.write_text(digest_md, encoding="utf-8")

    total_signals = len(funding_signals_raw) + len(policy_signals_raw) + len(market_signals_raw)
    result = {
        "saved": True,
        "report_path": str(report_path),
        "digest_path": str(digest_path),
        "news_count": len(all_news_raw),
        "signal_count": total_signals,
    }
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate full daily intelligence brief.")
    parser.add_argument("--date", default="", help="Target date (YYYY-MM-DD). Defaults to today.")
    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()
    date = args.date if args.date else _today_str()
    result = synthesize(date)
    print(json.dumps(result, indent=2))
