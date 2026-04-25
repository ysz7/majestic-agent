"""Briefing tool — full market/tech briefing with predictions and capital flows."""
from __future__ import annotations

from datetime import datetime

from majestic.tools.registry import tool

BRIEFING_PROMPT = """You are a personal analyst. Based on the data below, write a comprehensive briefing covering what is happening in the world, where things are heading, and what it means for someone who builds products and makes investments.

=== TOP NEWS & SIGNALS (last {days} days) ===
{news_context}

=== MARKET DATA ===
{market_context}

---

# 🌍 Briefing — {date}

## ⚡ What's happening in the world right now
[5 most important themes — not just tech. For each: one sentence what it is + one sentence why it matters.]

## 🔥 The dominant story of the period
[The single most significant development. 3-4 sentences: what, who, what changes, how long it might last.]

## 🧭 Where each segment is moving
Each bullet MUST be a complete sentence: who + specific action + reason from data.
- **Retail investors:** concrete action + reason
- **Large corporations:** where budget and attention is going
- **SMBs:** tools, pivots, or struggles — cite the signal
- **Developers / indie builders:** what they are building — cite GitHub + HN signals
- **Micro-SaaS founders:** growing, shrinking, or pivoting
- **End consumers:** behavior shifts — cite Google Trends or Reddit
- **Governments / regulators:** regulation target or funding focus

## 🔮 Predictions (next 30–90 days)
5 bold, specific, falsifiable predictions. Each:
**[Prediction]**
Probability: X% | Signals: 2-3 items | Wildcard: one thing that could prevent it

## 📊 Market snapshot
[Describe price movements from market data. 2-3 sentences on risk appetite.]

## 💸 Money flows — where money is moving RIGHT NOW
For each confirmed SECTOR (2+ independent signals):
**[Sector name — specific, not "AI" but "AI agents for inbound lead qualification"]**
[2-3 sentences: who pays whom, for what, why now. Sources: article titles]
Maximum 5 sectors. If fewer than 2 pass 2-signal rule: "Insufficient confirmed signals."

## 📈 Where to invest now
- **Crypto:** [BUY/HOLD/AVOID] — reason
- **Stocks:** [BUY/HOLD/AVOID] — reason with sectors
- **Sector to enter:** opportunity + timing window
- **What to avoid:** asset/sector with negative signals

## ✅ 3 things worth a closer look this week
[3 specific items from data — each with one line on why it matters]
"""

PREDICTIONS_PROMPT = """You are a strategic analyst mapping CAUSAL CHAINS between domains.

=== NEWS & SIGNALS (last {days} days, organized by confirmed themes) ===
{news_context}

=== MARKET DATA ===
{market_context}

CONFIRMED themes (2+ independent organic sources) = HIGH CONFIDENCE.
Single-source = context only. Product Hunt = marketing, demand NOT confirmed.

# 🔮 Predictions — {date}

## 🧭 Segment movement map
Only include segments with CONFIRMED signals. Each bullet: who + specific action + reason.
- **Retail investors:** action + reason
- **Enterprises:** where budget goes — cite confirmed signal
- **SMBs:** tools, pivots — cite confirmed signal
- **Developers:** building or abandoning — cite GitHub + HN
- **Consumers:** behavior shifts — cite Google Trends or Reddit
- **Micro-SaaS founders:** growing or pivoting — toward what
- **Governments:** regulation target — cite news signal

## 🎯 Predictions with probabilities
10 predictions, mixed time horizons. Each specific and falsifiable.
**[Prediction — name specific company, technology, or measurable event]**
⏱ Horizon: [timeframe] | 📊 Probability: X% | 🔗 Signals: 2-3 confirmed items | ⚡ Why: causal mechanism | ⚠️ Wildcard: invalidating event

## 📈 Market & investment signals
**Strongest BUY signal:** [specific asset] — [2+ independent signals] — [time window]
**Strongest AVOID signal:** [specific asset] — [negative signals] — [why now]
**Contrarian opportunity:** [niche/asset consensus hasn't priced in] — Evidence: [signals]
**Cascade risk:** [specific event → cascade] — Mechanism: [...] | Probability: X%

## 🚀 Trending niches to enter (4-6 niches, confirmed by 2+ organic sources)

## ⚡ Highest-confidence call
3-4 sentences: #1 prediction with strongest multi-source support. What to do RIGHT NOW.
"""

MONEY_FLOWS_PROMPT = """You are a financial intelligence analyst. Identify sectors where money is ACTUALLY moving — only confirmed transactions backed by evidence.

=== NEWS & SIGNALS (last {days} days) ===
{news_context}

For each confirmed SECTOR write a card:
**[Sector — specific, not "AI" but "AI agents for inbound lead qualification"]**
[2-3 sentences: who pays whom, for what, why now. Sources: article titles]

RULES:
1. Only 2+ INDEPENDENT signals from DIFFERENT sources
2. If signals contradict — note range, cite both
3. No proof = not included
4. Sort by number of confirming signals
5. Max 7 sectors
6. If <2 sectors qualify: "Insufficient confirmed signals in current data period."

# 💸 Money Flows — {date}
_Period: last {days} days | Only sectors with 2+ confirmed signals_
"""

QUICK_SUMMARY_PROMPT = """You are a personal analyst. Fresh data was just collected. Below are ONLY NEW items (duplicates filtered).

{context}

---

## 🌍 What's happening right now ({count} new items)
Only include sections with actual data — skip sections with no data:
**📰 World News:** top headlines
**🔬 arXiv:** most significant new papers
**🟠 Hacker News:** most discussed topics
**🔴 Reddit:** community reactions
**🐙 GitHub:** trending repos
**🔶 Product Hunt:** notable launches
**💻 Dev.to:** top articles
**📈 Google Trends:** search spikes

## 🔥 The most important story right now
[Pick the single most significant item. 2-3 sentences: what, why it matters, what changes.]

## 💡 Signal worth acting on
[One concrete opportunity or trend. 2-3 sentences.]

## ⚡ 3 items worth a closer look
[3 specific titles — each with one line on why it matters.]
"""


@tool(
    name="get_briefing",
    description=(
        "Generate a full analytical briefing covering recent tech/market signals, "
        "predictions, and capital flow analysis. "
        "Use when the user asks for a briefing, predictions, forecasts, or capital flows."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "days": {"type": "integer", "description": "Days of data to include (default 14)"},
            "focus": {
                "type": "string",
                "enum": ["full", "predictions", "flows"],
                "description": "full = complete briefing; predictions = forecasts only; flows = capital flows only",
            },
        },
    },
)
def get_briefing(days: int = 14, focus: str = "full") -> str:
    try:
        if focus == "predictions":
            return generate_predictions(days=days)
        if focus == "flows":
            return generate_money_flows(days=days)
        return generate_briefing(days=days)
    except Exception as e:
        return f"Briefing error: {e}"


def _llm_call(prompt: str, operation: str) -> str:
    from majestic.llm import get_provider
    from majestic.token_tracker import track
    from majestic.tools.research.intel_context import _lang_wrap
    resp = get_provider().complete([{"role": "user", "content": _lang_wrap(prompt)}])
    try:
        um = resp.usage
        if um:
            track(um.input_tokens or 0, um.output_tokens or 0, operation)
    except Exception:
        pass
    return resp.content


def generate_briefing(days: int = 14) -> str:
    from majestic.tools.research.intel_context import _build_briefing_context
    from majestic.tools.research.market_data import market_context_for_llm
    from majestic.constants import EXPORTS_DIR

    news_ctx   = _build_briefing_context(days=days, top_per_source=60)
    if not news_ctx:
        return "No data. Run /research first."
    market_ctx = market_context_for_llm(snapshots=10) or "No market data yet."
    date_str   = datetime.now().strftime("%Y-%m-%d %H:%M")
    prompt     = BRIEFING_PROMPT.format(days=days, news_context=news_ctx[:12000], market_context=market_ctx[:3000], date=date_str)
    result     = _llm_call(prompt, "trends.briefing")
    try:
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        (EXPORTS_DIR / f"briefing_{datetime.now().strftime('%Y%m%d_%H%M')}.md").write_text(result, encoding="utf-8")
    except Exception:
        pass
    return result


def generate_predictions(days: int = 14) -> str:
    from majestic.tools.research.intel_context import _build_thematic_context
    from majestic.tools.research.market_data import market_context_for_llm
    from majestic.constants import EXPORTS_DIR

    news_ctx   = _build_thematic_context(days=days)
    if not news_ctx:
        return "No data. Run /research first."
    market_ctx = market_context_for_llm(snapshots=10) or "No market data yet."
    date_str   = datetime.now().strftime("%Y-%m-%d %H:%M")
    prompt     = PREDICTIONS_PROMPT.format(days=days, news_context=news_ctx[:14000], market_context=market_ctx[:3000], date=date_str)
    result     = _llm_call(prompt, "trends.predictions")
    try:
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        (EXPORTS_DIR / f"predictions_{datetime.now().strftime('%Y%m%d_%H%M')}.md").write_text(result, encoding="utf-8")
    except Exception:
        pass
    return result


def generate_money_flows(days: int = 14) -> str:
    from majestic.tools.research.intel_context import _build_briefing_context
    from majestic.constants import EXPORTS_DIR

    news_ctx = _build_briefing_context(days=days, top_per_source=60)
    if not news_ctx:
        return "No data. Run /research first."
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    prompt   = MONEY_FLOWS_PROMPT.format(days=days, news_context=news_ctx[:14000], date=date_str)
    result   = _llm_call(prompt, "trends.money_flows")
    try:
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        (EXPORTS_DIR / f"money_flows_{datetime.now().strftime('%Y%m%d_%H%M')}.md").write_text(result, encoding="utf-8")
    except Exception:
        pass
    return result


def quick_summary_from_new(new_items: list) -> str:
    if not new_items:
        return "No new items found — everything was already in the database."
    sections = {}
    src_labels = {
        "hackernews": "HACKER NEWS", "reddit": "REDDIT", "github_trending": "GITHUB TRENDING",
        "producthunt": "PRODUCT HUNT", "mastodon": "MASTODON", "devto": "DEV.TO",
        "google_trends": "GOOGLE TRENDS", "newsapi": "NEWS (WORLD)", "arxiv": "ARXIV PAPERS",
    }
    for item in new_items:
        src   = item.get("source", "other")
        title = item.get("title", "")
        desc  = item.get("description") or item.get("selftext") or ""
        score = item.get("score") or item.get("stars") or ""
        line  = f"• {title}"
        if desc:
            line += f" — {desc[:100]}"
        if score:
            line += f" [{score}]"
        sections.setdefault(src, []).append(line)
    parts   = [f"=== {src_labels.get(s, s.upper())} ({len(lines)} new) ===\n" + "\n".join(lines[:25]) for s, lines in sections.items()]
    context = "\n\n".join(parts)
    prompt  = QUICK_SUMMARY_PROMPT.format(context=context[:7000], count=len(new_items))
    return _llm_call(prompt, "trends.quick_summary")
