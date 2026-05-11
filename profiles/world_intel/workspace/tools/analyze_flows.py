"""
analyze_flows.py — Aggregate funding signals into capital flow patterns.

Usage:
    python analyze_flows.py today
    python analyze_flows.py --date 2026-05-11
    python analyze_flows.py week [--week 2026-W19]
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
# Segment / Stage maps
# ---------------------------------------------------------------------------

SEGMENT_MAP = {
    "AI/ML": ["ai", "ml", "machine learning", "llm", "gpt", "artificial intelligence", "computer vision"],
    "Cloud": ["cloud", "infrastructure", "saas", "platform", "devops", "kubernetes"],
    "Cybersecurity": ["security", "cyber", "compliance", "soc", "identity"],
    "Fintech": ["fintech", "payments", "banking", "lending", "insurance", "wealth"],
    "Healthtech": ["health", "medical", "biotech", "diagnostic", "clinical", "pharma"],
    "Climate tech": ["climate", "clean", "solar", "wind", "carbon", "sustainability"],
    "Nuclear": ["nuclear", "smr", "fusion", "fission", "reactor"],
    "Defense tech": ["defense", "military", "drone", "autonomous vehicle", "surveillance"],
    "Robotics": ["robot", "automation", "warehouse", "manufacturing"],
    "Crypto/Web3": ["crypto", "blockchain", "web3", "defi", "nft", "token"],
    "Developer tools": ["developer", "devtools", "api", "sdk", "open source"],
    "Edtech": ["education", "learning", "training", "skill"],
    "Logistics": ["logistics", "supply chain", "shipping", "fulfillment"],
    "Space": ["space", "satellite", "rocket", "orbit"],
}

STAGE_MAP = {
    "Seed": ["seed", "pre-seed", "angel"],
    "Early": ["series a", "series-a"],
    "Growth": ["series b", "series-b", "series c", "series-c"],
    "Pre-IPO": ["series d", "series e", "growth equity", "late stage"],
}

# ---------------------------------------------------------------------------
# Helpers
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


def _classify_segment(text: str) -> str:
    """Return first matching segment name or 'Other'."""
    lower = text.lower()
    for segment, keywords in SEGMENT_MAP.items():
        for kw in keywords:
            if kw in lower:
                return segment
    return "Other"


def _classify_stage(text: str) -> str:
    """Return first matching stage name or 'Unknown'."""
    lower = text.lower()
    for stage, keywords in STAGE_MAP.items():
        for kw in keywords:
            if kw in lower:
                return stage
    return "Unknown"


def _parse_amount(data: dict) -> float:
    """Try to extract a USD amount in millions from signal data_json fields."""
    for field in ("amount_usd_millions", "amount_millions", "amount"):
        val = data.get(field)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    return 0.0


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _prior_date(date_str: str) -> str:
    """Return the date one day before date_str."""
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return (d - timedelta(days=1)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def analyze_date(date: str) -> dict:
    """Aggregate funding signals for a single date into segment flows."""
    # 1. Load funding signals
    signals_raw = _run_tool("db_signals.py", "get_funding_signals", "--date", date)
    if not isinstance(signals_raw, list):
        signals_raw = []

    # 2. Parse and classify each signal
    segment_totals: dict[str, dict] = {}  # segment -> {amount, deals}
    stage_totals: dict[str, dict] = {}

    for sig in signals_raw:
        try:
            data = json.loads(sig.get("data_json", "{}"))
        except (json.JSONDecodeError, AttributeError):
            data = {}

        text = " ".join(str(v) for v in [
            data.get("sector", ""),
            data.get("niche", ""),
            data.get("company", ""),
            data.get("description", ""),
            sig.get("type", ""),
        ])

        segment = _classify_segment(text)
        stage_text = " ".join(str(v) for v in [
            data.get("stage", ""),
            data.get("round", ""),
            data.get("series", ""),
        ])
        stage = _classify_stage(stage_text)

        amount = _parse_amount(data)

        # Aggregate segment
        if segment not in segment_totals:
            segment_totals[segment] = {"amount": 0.0, "deals": 0}
        segment_totals[segment]["amount"] += amount
        segment_totals[segment]["deals"] += 1

        # Aggregate stage
        if stage not in stage_totals:
            stage_totals[stage] = {"amount": 0.0, "deals": 0}
        stage_totals[stage]["amount"] += amount
        stage_totals[stage]["deals"] += 1

    total_amount = sum(v["amount"] for v in segment_totals.values())
    total_deals = sum(v["deals"] for v in segment_totals.values())

    # 3. Detect outlier: any single deal > 80% of daily volume
    OUTLIER_THRESHOLD = 0.80
    outlier_detected = False
    for sig in signals_raw:
        try:
            data = json.loads(sig.get("data_json", "{}"))
        except (json.JSONDecodeError, AttributeError):
            data = {}
        deal_amount = _parse_amount(data)
        if total_amount > 0 and deal_amount / total_amount > OUTLIER_THRESHOLD:
            outlier_detected = True
            break

    # 4. Calculate momentum and upsert into flows.db
    prior_date = _prior_date(date)
    segments_out = []

    for segment, agg in sorted(segment_totals.items(), key=lambda x: x[1]["amount"], reverse=True):
        current_amount = agg["amount"]
        current_deals = agg["deals"]

        # Detect if this segment is an outlier (> 80% of total)
        is_seg_outlier = (
            total_amount > 0 and current_amount / total_amount > OUTLIER_THRESHOLD
        )

        # Load prior period data for momentum
        prior_flows = _run_tool("db_flows.py", "get_by_segment", segment, "--limit", "30")
        prior_amount = 0.0
        if isinstance(prior_flows, list):
            for flow in prior_flows:
                if flow.get("period") == prior_date:
                    prior_amount = float(flow.get("total_amount", 0.0))
                    break

        if prior_amount > 0:
            ratio = current_amount / prior_amount
            if ratio > 1.5:
                momentum = "accelerating"
            elif ratio < 0.67:
                momentum = "decelerating"
            else:
                momentum = "stable"
        else:
            momentum = "stable"

        # Upsert into flows.db
        flow_record = {
            "segment": segment,
            "period": date,
            "period_type": "daily",
            "total_amount": current_amount,
            "deal_count": current_deals,
            "momentum": momentum,
            "is_outlier": 1 if is_seg_outlier else 0,
        }
        _run_tool("db_flows.py", "upsert", json.dumps(flow_record))

        segments_out.append({
            "segment": segment,
            "amount": current_amount,
            "deals": current_deals,
            "momentum": momentum,
        })

    # 5. Build and return result
    result = {
        "date": date,
        "total_amount_usd_millions": total_amount,
        "deal_count": total_deals,
        "segments": segments_out,
        "stages": [
            {"stage": stage, "amount": agg["amount"], "deals": agg["deals"]}
            for stage, agg in sorted(stage_totals.items(), key=lambda x: x[1]["amount"], reverse=True)
        ],
        "outlier_detected": outlier_detected,
    }
    return result


def analyze_week(week_str: str) -> dict:
    """Aggregate funding signals for an entire ISO week."""
    # Parse ISO week: e.g. "2026-W19"
    year, wnum = week_str.split("-W")
    year, wnum = int(year), int(wnum)
    # ISO week Monday
    jan4 = datetime(year, 1, 4)
    week_start = jan4 + timedelta(weeks=wnum - 1, days=-jan4.weekday())
    dates = [(week_start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

    combined_segments: dict[str, dict] = {}
    combined_deals = 0
    outlier_any = False

    for date in dates:
        daily = analyze_date(date)
        combined_deals += daily["deal_count"]
        if daily["outlier_detected"]:
            outlier_any = True
        for seg in daily["segments"]:
            s = seg["segment"]
            if s not in combined_segments:
                combined_segments[s] = {"amount": 0.0, "deals": 0}
            combined_segments[s]["amount"] += seg["amount"]
            combined_segments[s]["deals"] += seg["deals"]

    total_amount = sum(v["amount"] for v in combined_segments.values())
    segments_out = [
        {"segment": s, "amount": v["amount"], "deals": v["deals"], "momentum": "stable"}
        for s, v in sorted(combined_segments.items(), key=lambda x: x[1]["amount"], reverse=True)
    ]

    return {
        "week": week_str,
        "dates": dates,
        "total_amount_usd_millions": total_amount,
        "deal_count": combined_deals,
        "segments": segments_out,
        "outlier_detected": outlier_any,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aggregate funding signals into capital flow patterns.")
    sub = parser.add_subparsers(dest="command")

    # today
    sub.add_parser("today", help="Analyze today's funding signals.")

    # --date <date>
    parser.add_argument("--date", default="", help="Specific date (YYYY-MM-DD).")

    # week
    p_week = sub.add_parser("week", help="Analyze a full ISO week.")
    p_week.add_argument("--week", default="", help="ISO week (e.g. 2026-W19). Defaults to current week.")

    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    command = getattr(args, "command", None)

    if command == "week":
        if args.week:
            week_str = args.week
        else:
            today = datetime.now(timezone.utc)
            week_str = today.strftime("%Y-W%W")
        result = analyze_week(week_str)
    else:
        if command == "today":
            date = _today_str()
        elif args.date:
            date = args.date
        else:
            date = _today_str()
        result = analyze_date(date)

    print(json.dumps(result, indent=2))
