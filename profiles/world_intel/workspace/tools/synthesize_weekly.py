"""
synthesize_weekly.py — Generate weekly deep intelligence report.

Usage:
    python synthesize_weekly.py
    python synthesize_weekly.py --week 2026-W19
"""

import json
import sys
import subprocess
import argparse
from datetime import datetime, timezone, timedelta
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
# ISO week helpers
# ---------------------------------------------------------------------------

def _current_week_str() -> str:
    today = datetime.now(timezone.utc)
    return today.strftime("%Y-W%W")


def _week_dates(week_str: str) -> list[str]:
    """Return list of 7 date strings (Mon-Sun) for the given ISO week string."""
    year_str, wnum_str = week_str.split("-W")
    year, wnum = int(year_str), int(wnum_str)
    jan4 = datetime(year, 1, 4)
    week_start = jan4 + timedelta(weeks=wnum - 1, days=-jan4.weekday())
    return [(week_start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]


def _prior_week_str(week_str: str) -> str:
    """Return the ISO week string for the week before the given one."""
    dates = _week_dates(week_str)
    prior_monday = datetime.strptime(dates[0], "%Y-%m-%d") - timedelta(weeks=1)
    return prior_monday.strftime("%Y-W%W")


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def synthesize_week(week_str: str) -> dict:
    env = _load_env()

    dates = _week_dates(week_str)
    week_start = dates[0]
    week_end = dates[-1]

    # 1. Load all news for the week (one call per day)
    all_news: list[dict] = []
    for date in dates:
        news = _run_tool("db_news.py", "get_by_date", date)
        if isinstance(news, list):
            all_news.extend(news)

    # 2. Load all funding signals for the week
    all_funding: list[dict] = []
    for date in dates:
        sigs = _run_tool("db_signals.py", "get_funding_signals", "--date", date)
        if isinstance(sigs, list):
            all_funding.extend(sigs)

    all_policy: list[dict] = []
    for date in dates:
        sigs = _run_tool("db_signals.py", "get_policy_signals", "--date", date)
        if isinstance(sigs, list):
            all_policy.extend(sigs)

    all_market: list[dict] = []
    for date in dates:
        sigs = _run_tool("db_signals.py", "get_by_type", "market_move", "--date", date)
        if isinstance(sigs, list):
            all_market.extend(sigs)

    # 3. Aggregate flow data for the week (per day, sum up)
    segment_totals: dict[str, dict] = {}
    for date in dates:
        flows = _run_tool("db_flows.py", "get_top_segments", date, "--n", "20")
        if isinstance(flows, list):
            for flow in flows:
                seg = flow.get("segment", "")
                amt = float(flow.get("total_amount", 0))
                deals = int(flow.get("deal_count", 0))
                if seg not in segment_totals:
                    segment_totals[seg] = {"amount": 0.0, "deals": 0}
                segment_totals[seg]["amount"] += amt
                segment_totals[seg]["deals"] += deals

    # 4. Load prior week flows for comparison
    prior_week_str = _prior_week_str(week_str)
    prior_segment_totals: dict[str, dict] = {}
    prior_dates = _week_dates(prior_week_str)
    for date in prior_dates:
        flows = _run_tool("db_flows.py", "get_top_segments", date, "--n", "20")
        if isinstance(flows, list):
            for flow in flows:
                seg = flow.get("segment", "")
                amt = float(flow.get("total_amount", 0))
                if seg not in prior_segment_totals:
                    prior_segment_totals[seg] = {"amount": 0.0, "deals": 0}
                prior_segment_totals[seg]["amount"] += amt

    total_amount = sum(v["amount"] for v in segment_totals.values())
    total_deals = sum(v["deals"] for v in segment_totals.values())

    # Sort segments by amount
    top_segments = sorted(segment_totals.items(), key=lambda x: x[1]["amount"], reverse=True)

    # --- Parse funding signals ---
    funding_parsed = []
    for sig in all_funding:
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
        funding_parsed.append((amount, data))
    funding_parsed.sort(key=lambda x: x[0], reverse=True)

    # Prepare LLM prompt data
    funding_summary = "\n".join(
        f"- {d.get('company', 'Unknown')}: ${a:.1f}M ({d.get('stage', '')} | {d.get('niche', '')} | {d.get('date', '')})"
        for a, d in funding_parsed[:20]
    )
    current_flows_summary = "\n".join(
        f"- {seg}: ${v['amount']:.1f}M ({v['deals']} deals)"
        for seg, v in top_segments[:10]
    )
    prior_flows_summary = "\n".join(
        f"- {seg}: ${v['amount']:.1f}M"
        for seg, v in sorted(prior_segment_totals.items(), key=lambda x: x[1]["amount"], reverse=True)[:10]
    )
    top_news_for_llm = "\n".join(
        f"- [{item.get('date', '')}] {item.get('headline', '')} (importance={item.get('importance', 3)})"
        for item in sorted(all_news, key=lambda x: int(x.get("importance", 3)), reverse=True)[:20]
    )

    # --- LLM calls ---

    week_narrative = _call_llm(
        prompt=(
            f"Week: {week_str} ({week_start} to {week_end})\n\n"
            f"Top news:\n{top_news_for_llm}\n\n"
            f"Capital flows:\n{current_flows_summary}\n\n"
            f"Funding rounds:\n{funding_summary}"
        ),
        system=(
            "Write 5 bullet points for the most important things that happened this week in global markets, "
            "tech, and capital flows. Be specific with names, amounts, and dates."
        ),
        env=env,
        max_tokens=700,
    )

    thesis_shifts = _call_llm(
        prompt=(
            f"Current week ({week_str}) capital flows:\n{current_flows_summary}\n\n"
            f"Prior week ({prior_week_str}) capital flows:\n{prior_flows_summary}"
        ),
        system=(
            "Compare this week vs prior week capital flows. What changed in how money is thinking? "
            "New themes emerging? Old themes fading? Be specific."
        ),
        env=env,
        max_tokens=600,
    )

    # Sector deep dives (top 2-3 segments by volume)
    sector_dives = []
    for seg, v in top_segments[:3]:
        seg_funding = "\n".join(
            f"- {d.get('company', 'Unknown')}: ${a:.1f}M"
            for a, d in funding_parsed[:20]
            if (d.get("niche") or d.get("sector") or "").lower() in seg.lower()
               or seg.lower() in (d.get("niche") or d.get("sector") or "").lower()
        ) or f"Total flow: ${v['amount']:.1f}M across {v['deals']} deals"

        dive = _call_llm(
            prompt=f"Sector: {seg}\nWeek: {week_str}\nFlow: ${v['amount']:.1f}M, {v['deals']} deals\n\nFunding:\n{seg_funding}",
            system=(
                f"Write a 3-4 sentence deep dive on {seg} sector activity this week. "
                "What companies are getting funded? What's driving activity? What are the implications?"
            ),
            env=env,
            max_tokens=400,
        )
        sector_dives.append((seg, dive))

    emerging_niches = _call_llm(
        prompt=f"Funding signals this week ({week_str}):\n{funding_summary}",
        system=(
            "Which investment niches appeared for the first time in funding data this week? "
            "What made them emerge? Give 2-3 examples with context."
        ),
        env=env,
        max_tokens=500,
    )

    # High-importance news with no corresponding funding
    high_importance_news = "\n".join(
        f"- [{item.get('date', '')}] {item.get('headline', '')} (category={item.get('category', '')})"
        for item in sorted(all_news, key=lambda x: int(x.get("importance", 3)), reverse=True)
        if int(item.get("importance", 3)) >= 4
    )[:2000]
    contrarian_signals = _call_llm(
        prompt=(
            f"High-importance news this week:\n{high_importance_news}\n\n"
            f"Sectors that received funding:\n{current_flows_summary}"
        ),
        system=(
            "Which high-importance news items this week had no corresponding funding activity? "
            "What is being ignored by investors? Be specific and contrarian."
        ),
        env=env,
        max_tokens=500,
    )

    # --- Build capital flow map section ---
    max_amount = top_segments[0][1]["amount"] if top_segments else 1.0
    flow_map_lines = []
    for seg, v in top_segments:
        bar_len = int(round(v["amount"] / max_amount * 30))
        bar = "█" * bar_len
        prior_amt = prior_segment_totals.get(seg, {}).get("amount", 0.0)
        if prior_amt > 0:
            ratio = v["amount"] / prior_amt
            trend = "▲" if ratio > 1.5 else ("▼" if ratio < 0.67 else "→")
        else:
            trend = "→"
        flow_map_lines.append(
            f"  {trend} {seg:<22} {bar:<30}  ${v['amount']:.1f}M  ({v['deals']} deals)"
        )
    flow_map_section = "\n".join(flow_map_lines) if flow_map_lines else "_No flow data for this week._"

    # --- Full news index ---
    news_index_lines = []
    for item in sorted(all_news, key=lambda x: (x.get("date", ""), -int(x.get("importance", 3)))):
        headline = item.get("headline", "")
        source = item.get("source", "")
        date = item.get("date", "")
        url = item.get("source_url", "")
        news_index_lines.append(f"- [{date}] {headline} — [{source}]({url})")
    news_index = "\n".join(news_index_lines) if news_index_lines else "_No news collected for this week._"

    # --- Policy section ---
    policy_bullets = []
    for sig in all_policy:
        try:
            data = json.loads(sig.get("data_json", "{}"))
        except (json.JSONDecodeError, AttributeError):
            data = {}
        desc = data.get("description") or data.get("title") or data.get("policy") or str(data)
        policy_bullets.append(f"- {desc}")
    policy_section = "\n".join(policy_bullets) if policy_bullets else "_No policy signals this week._"

    # --- Sector deep dives section ---
    sector_section_parts = []
    for seg, dive in sector_dives:
        sector_section_parts.append(f"### {seg}\n{dive}")
    sector_section = "\n\n".join(sector_section_parts) if sector_section_parts else "_Insufficient data._"

    # --- Outlook (brief summary) ---
    outlook = _call_llm(
        prompt=(
            f"Week in review ({week_str}): Total funding ${total_amount:.1f}M across {total_deals} deals.\n"
            f"Top sectors: {', '.join(seg for seg, _ in top_segments[:5])}\n"
            f"Week narrative:\n{week_narrative}"
        ),
        system=(
            "Write a 2-3 sentence forward-looking outlook for the coming week based on this week's signals. "
            "What should investors watch? What trends are likely to continue or reverse?"
        ),
        env=env,
        max_tokens=300,
    )

    # --- Build weekly report ---
    report_md = f"""# WEEKLY INTELLIGENCE REPORT — {week_str}
**Period:** {week_start} to {week_end}
**Generated:** {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}

---

## WEEK IN REVIEW

{week_narrative}

---

## CAPITAL FLOW MAP

Total: ${total_amount:.1f}M across {total_deals} deals

{flow_map_section}

---

## INVESTMENT THESIS SHIFTS

{thesis_shifts}

---

## SECTOR DEEP DIVES

{sector_section}

---

## POLICY IMPACT

{policy_section}

---

## GEOGRAPHIC SPOTLIGHT

_Geographic breakdown requires geo-tagged signal data._

---

## EMERGING NICHES

{emerging_niches}

---

## CONTRARIAN SIGNALS

{contrarian_signals}

---

## FULL NEWS INDEX

{news_index}

---

## OUTLOOK

{outlook}
"""

    # Save report
    report_dir = _OUTPUT_DIR / "reports" / "weekly"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{week_str}.md"
    report_path.write_text(report_md, encoding="utf-8")

    result = {
        "saved": True,
        "report_path": str(report_path),
        "week": week_str,
        "news_count": len(all_news),
        "signal_count": len(all_funding) + len(all_policy) + len(all_market),
    }
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate weekly deep intelligence report.")
    parser.add_argument("--week", default="", help="ISO week string (e.g. 2026-W19). Defaults to current week.")
    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()
    week_str = args.week if args.week else _current_week_str()
    result = synthesize_week(week_str)
    print(json.dumps(result, indent=2))
