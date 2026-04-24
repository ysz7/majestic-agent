"""
Trend Analyzer — trend, niche, and opportunity analysis
Daily Briefing — morning digest
"""

import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict

from core.intel import load_feed, INTEL_DIR
from core.rag_engine import ask, llm
from langchain_core.messages import HumanMessage

# ── Signal quality weights (same logic as agent.py) ─────────────────────────────
_SOURCE_TRUST: Dict[str, float] = {
    "hackernews":      1.0,
    "reddit":          0.9,
    "github_trending": 1.0,
    "newsapi":         1.0,
    "arxiv":           0.95,
    "google_trends":   0.8,
    "mastodon":        0.65,
    "devto":           0.6,
    "producthunt":     0.2,   # marketing, not organic signal
}

_STOP_WORDS = {
    "about", "after", "again", "also", "been", "before", "being", "between",
    "could", "does", "doing", "during", "each", "from", "have", "having",
    "here", "into", "just", "like", "more", "most", "need", "only", "other",
    "over", "same", "should", "some", "such", "than", "that", "their",
    "them", "then", "there", "these", "they", "this", "those", "through",
    "under", "very", "want", "were", "what", "when", "where", "which",
    "while", "will", "with", "would", "your", "using", "build", "built",
    "make", "made", "open", "source", "project", "based", "model", "tool",
    "tools", "first", "large", "small", "data", "works", "work", "write",
}

BRIEFING_DIR = Path(__file__).parent.parent / "data" / "exports"
BRIEFING_DIR.mkdir(parents=True, exist_ok=True)


# ── Raw feed → structured context ───────────────────────────────────────────────

def _build_feed_context(hours: int = 24, max_items: int = 120) -> str:
    """Build a text summary of recent intel for LLM analysis."""
    items = load_feed(limit=max_items)
    if not items:
        return ""

    cutoff = datetime.now() - timedelta(hours=hours)
    recent = []
    for item in items:
        try:
            ts = datetime.fromisoformat(item.get("ts", ""))
            if ts >= cutoff:
                recent.append(item)
        except Exception:
            recent.append(item)  # include if no ts

    recent = recent[:max_items]
    if not recent:
        return ""

    sections: Dict[str, List[str]] = {}
    for item in recent:
        source = item.get("source", "other")
        title  = item.get("title", "")
        desc   = item.get("description") or item.get("selftext") or ""
        score  = item.get("score") or item.get("stars") or ""
        line   = f"• {title}"
        if desc:
            line += f" — {desc[:120]}"
        if score:
            line += f" [{score}]"
        sections.setdefault(source, []).append(line)

    parts = []
    labels = {
        "hackernews":      "HACKER NEWS",
        "reddit":          "REDDIT",
        "github_trending": "GITHUB TRENDING",
        "producthunt":     "PRODUCT HUNT",
        "mastodon":        "MASTODON",
        "devto":           "DEV.TO",
        "google_trends":   "GOOGLE TRENDS",
        "newsapi":         "NEWS (WORLD)",
        "arxiv":           "ARXIV PAPERS",
    }
    for src, lines in sections.items():
        label = labels.get(src, src.upper())
        parts.append(f"=== {label} ({len(lines)} items) ===\n" + "\n".join(lines[:30]))

    return "\n\n".join(parts)


def _build_briefing_context(days: int = 30, top_per_source: int = 40) -> str:
    """
    Build context for /briefing using up to `days` days of feed data.
    To avoid LLM overload, picks top items by score/stars from each source.
    """
    items = load_feed(limit=3000)
    if not items:
        return ""

    cutoff = datetime.now() - timedelta(days=days)
    recent = []
    for item in items:
        try:
            ts = datetime.fromisoformat(item.get("ts", ""))
            if ts >= cutoff:
                recent.append(item)
        except Exception:
            recent.append(item)

    if not recent:
        return ""

    # Group by source, sort each group by score desc, take top N
    from collections import defaultdict
    groups: Dict[str, list] = defaultdict(list)
    for item in recent:
        groups[item.get("source", "other")].append(item)

    labels = {
        "hackernews":      "HACKER NEWS",
        "reddit":          "REDDIT",
        "github_trending": "GITHUB TRENDING",
        "producthunt":     "PRODUCT HUNT",
        "mastodon":        "MASTODON",
        "devto":           "DEV.TO",
        "google_trends":   "GOOGLE TRENDS",
        "newsapi":         "NEWS (WORLD)",
        "arxiv":           "ARXIV PAPERS",
    }

    parts = []
    total = 0
    for src, src_items in groups.items():
        # Sort by CCW desc first, then by engagement score
        sorted_items = sorted(
            src_items,
            key=lambda x: (
                x.get("ccw", 0),
                int(str(x.get("score") or x.get("stars") or 0).replace(",", "") or 0),
            ),
            reverse=True,
        )[:top_per_source]
        lines = []
        for item in sorted_items:
            title = item.get("title", "")
            desc  = item.get("description") or item.get("selftext") or ""
            score = item.get("score") or item.get("stars") or ""
            ccw   = item.get("ccw", 0)
            line  = f"• {title}"
            if desc:
                line += f" — {desc[:100]}"
            if score:
                line += f" [{score}]"
            if ccw >= 7:
                line += f" [CCW:{ccw}]"
            lines.append(line)
        label = labels.get(src, src.upper())
        total += len(lines)
        parts.append(f"=== {label} ({len(src_items)} items over {days}d, showing top {len(lines)}) ===\n" + "\n".join(lines))

    return "\n\n".join(parts)


# ── Thematic cross-source context ────────────────────────────────────────────────

def _build_thematic_context(days: int = 14, top_per_source: int = 40) -> str:
    """
    Build context organized by CONFIRMED THEMES (topics appearing in 2+ independent
    organic sources) rather than by source.
    Product Hunt is excluded from cluster confirmation.
    Gives LLM the pre-computed cross-niche signal map — not raw feed soup.
    """
    items = load_feed(limit=3000)
    if not items:
        return ""

    cutoff = datetime.now() - timedelta(days=days)
    recent: List[Dict] = []
    for item in items:
        try:
            ts = datetime.fromisoformat(item.get("ts", ""))
            if ts >= cutoff:
                recent.append(item)
        except Exception:
            recent.append(item)

    if not recent:
        return ""

    # ── Cluster organic items by keyword across sources ───────────────────────
    organic = [i for i in recent if _SOURCE_TRUST.get(i.get("source", ""), 0.5) >= 0.6]

    word_sources: Dict[str, set] = defaultdict(set)
    word_items:   Dict[str, list] = defaultdict(list)

    for item in organic:
        title  = item.get("title", "")
        desc   = (item.get("description") or item.get("selftext") or "")
        text   = (title + " " + desc).lower()
        src    = item.get("source", "")
        tokens = {
            w.strip(".,!?:;()[]'\"") for w in text.split()
            if len(w) >= 5 and w.strip(".,!?:;()[]'\"") not in _STOP_WORDS
        }
        for w in tokens:
            word_sources[w].add(src)
            word_items[w].append(item)

    # Keep only cross-source clusters (2+ independent organic sources)
    clusters = {
        w: {"sources": srcs, "items": word_items[w]}
        for w, srcs in word_sources.items()
        if len(srcs) >= 2
    }

    # Assign each item to its strongest cluster (avoid duplicate lines)
    item_best_cluster: Dict[str, str] = {}
    for w, data in sorted(clusters.items(), key=lambda x: -len(x[1]["sources"])):
        for item in data["items"]:
            title = item.get("title", "")
            if title not in item_best_cluster:
                item_best_cluster[title] = w

    # ── Build thematic sections ───────────────────────────────────────────────
    parts: List[str] = []
    seen_in_clusters: set = set()

    parts.append(
        "=== CONFIRMED CROSS-SOURCE THEMES ===\n"
        "(Each theme appears in 2+ independent organic sources — these are real signals, not hype)\n"
    )

    top_clusters = sorted(clusters.items(), key=lambda x: -len(x[1]["sources"]))[:18]
    for w, data in top_clusters:
        srcs_str = " + ".join(sorted(data["sources"]))
        cluster_lines: List[str] = []
        for item in data["items"]:
            title = item.get("title", "")
            if item_best_cluster.get(title) != w or title in seen_in_clusters:
                continue
            seen_in_clusters.add(title)
            src   = item.get("source", "")
            score = item.get("score") or item.get("stars") or ""
            desc  = (item.get("description") or item.get("selftext") or "")[:80]
            line  = f"  [{src}] {title}"
            if desc:
                line += f" — {desc}"
            if score:
                line += f" ({score})"
            cluster_lines.append(line)
            if len(cluster_lines) >= 4:
                break
        if cluster_lines:
            parts.append(
                f"\n── Theme [{w.upper()}] | {len(data['sources'])} sources: {srcs_str} ──\n"
                + "\n".join(cluster_lines)
            )

    # ── Single-source organic items (context only) ────────────────────────────
    labels = {
        "hackernews":      "HACKER NEWS",
        "reddit":          "REDDIT",
        "github_trending": "GITHUB TRENDING",
        "newsapi":         "WORLD NEWS",
        "arxiv":           "ARXIV PAPERS",
        "google_trends":   "GOOGLE TRENDS",
    }

    grouped: Dict[str, list] = defaultdict(list)
    for item in organic:
        src   = item.get("source", "")
        title = item.get("title", "")
        if title not in seen_in_clusters and _SOURCE_TRUST.get(src, 0) >= 0.6:
            grouped[src].append(item)

    single_parts: List[str] = []
    for src, src_items in grouped.items():
        label = labels.get(src, src.upper())
        sorted_items = sorted(
            src_items,
            key=lambda x: int(str(x.get("score") or x.get("stars") or 0).replace(",", "") or 0),
            reverse=True,
        )[:15]
        lines = []
        for item in sorted_items:
            title = item.get("title", "")
            score = item.get("score") or item.get("stars") or ""
            desc  = (item.get("description") or "")[:60]
            line  = f"  • {title}"
            if score:
                line += f" ({score})"
            lines.append(line)
        if lines:
            single_parts.append(f"[{label}]\n" + "\n".join(lines))

    if single_parts:
        parts.append(
            "\n\n=== SINGLE-SOURCE SIGNALS (weaker — use only if they reinforce a theme above) ===\n"
            + "\n".join(single_parts)
        )

    # ── Product Hunt separately ───────────────────────────────────────────────
    ph_items = [i for i in recent if i.get("source") == "producthunt"]
    if ph_items:
        ph_lines = []
        for item in ph_items[:15]:
            title = item.get("title", "")
            desc  = (item.get("description") or "")[:70]
            ph_lines.append(f"  • {title}" + (f" — {desc}" if desc else ""))
        parts.append(
            "\n\n=== PRODUCT HUNT LAUNCHES (marketing posts — niche exists, demand NOT confirmed) ===\n"
            + "\n".join(ph_lines)
        )

    return "\n".join(parts)


# ── Trend Analysis ───────────────────────────────────────────────────────────────

TREND_PROMPT = """You are a trend and business opportunity analyst.
Below is fresh data from Hacker News, Reddit, GitHub, and Product Hunt collected over the last 24 hours.

NOTE: Product Hunt items are company marketing posts — treat them as "niche exists" signals only,
NOT as evidence of market demand or trend confirmation.

{context}

---

Run a deep analysis and answer each question with concrete examples from the data above. No generic statements.

1. **🔥 Top 5 tech trends right now** — what is being discussed the most, and across which sources?

2. **💰 Where the money is** — which niches, products, or technologies are attracting attention and investment?
   Only count a niche as confirmed if it appears in 2+ independent organic sources (HN, Reddit, GitHub, news).

3. **🚀 Fast-growing opportunities** — which niche can be entered right now before it gets crowded?
   Explain what signals indicate it's growing AND not yet saturated.

4. **📈 GitHub insights** — which repos are spiking and why? What does this signal about where developers are investing effort?

5. **⚠️ Losing relevance** — what is fading, what to avoid? Cite specific signals.

6. **🎯 Personal recommendation** — if you had 3 months and wanted to launch something new, what would you pick based on this data?
   Ground your answer in confirmed cross-source signals, not single mentions.

CRITICAL OUTPUT RULE: Every sentence must be complete and unambiguous. Always state WHO + does WHAT precisely.
Bad: "AI companies take 60% more depending on language." Good: "AI companies charge 60% more for the same prompts from non-English users due to BPE tokenization inefficiency."
Bad: "People are moving away from platforms." Good: "Developers are migrating from centralized CI services to self-hosted alternatives after a series of account lockdowns."
If a fact would confuse the reader without context, include that context in the same sentence.
"""


def _lang_wrap(prompt: str) -> str:
    """Wrap prompt with language and currency instructions at both start and end."""
    from core.config import get_lang, get_currency
    lang = get_lang()
    currency = get_currency()
    instruction = (
        f"IMPORTANT: You MUST respond entirely in {lang}. All text including section headers must be in {lang}. "
        f"Always use {currency} for all prices, costs, revenue estimates, and monetary values."
    )
    return f"{instruction}\n\n{prompt}\n\n{instruction}"


def analyze_trends(hours: int = 24) -> str:
    """Run full trend analysis on recent intel."""
    ctx = _build_feed_context(hours=hours)
    if not ctx:
        return "⚠️ No data for analysis. Run /research first."

    prompt = _lang_wrap(TREND_PROMPT.format(context=ctx[:10000]))
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        from core.token_tracker import track_response
        track_response(response, "trends.analyze")
        return response.content
    except Exception as e:
        from core.error_logger import log_error
        log_error("trends.analyze", "LLM call failed", str(e))
        return f"❌ Analysis error: {e}"


BRIEFING_PROMPT_V2 = """You are a personal analyst. Based on the data below, write a comprehensive briefing covering what is happening in the world, where things are heading, and what it means for someone who builds products and makes investments.

=== TOP NEWS & SIGNALS (last {days} days, ranked by engagement and impact score) ===
{news_context}

=== MARKET DATA (last {snapshots} snapshots — crypto, stocks, forex) ===
{market_context}

---

# 🌍 Briefing — {date}
_Period: last {days} days_

## ⚡ What's happening in the world right now
[5 most important themes from the news data — not just tech, include geopolitics, science, business, society if present. For each: one sentence what it is + one sentence why it matters. These should be recurring signals across multiple sources, not one-off mentions.]

## 🔥 The dominant story of the period
[The single most significant development combining news + market data. 3-4 sentences: what is happening, who is driving it, what it changes, how long it might last.]

## 🧭 Where each segment is moving

Write one bullet per segment with clear signals. Be direct and opinionated — no hedging. Skip segments with no data.
Each bullet MUST be a complete sentence: who + specific action + reason from the data.
Bad: "Retail investors: buying renewable energy and leaving platforms after Google lockdowns." (fragmented, unclear)
Good: "Retail investors are shifting capital into renewable energy ETFs and moving to decentralized platforms after a wave of Google account lockdowns raised concerns about centralized dependency."

- **Retail investors / everyday people:** concrete action + reason from data
- **Large corporations / enterprises:** where budget and attention is specifically going
- **SMBs (small & medium business):** tools, pivots, or struggles — cite the signal
- **Developers / indie builders:** what they are building or abandoning — cite GitHub + HN signals
- **Micro-SaaS founders:** growing, shrinking, or pivoting — toward what exactly
- **End consumers (general public):** behavior shifts, spending, search interest — cite Google Trends or Reddit
- **Governments / regulators:** regulation target or funding focus — cite news signal

## 🔮 Predictions (next 30–90 days)

Write 5 bold, specific, falsifiable predictions based on cross-niche signal patterns. Each on its own line:

**[Specific prediction statement]**
Probability: X% | Signals: name 2-3 items from the data | Wildcard: one thing that could prevent it

Scale: 90%+ near-certain | 70–89% likely | 50–69% probable | 30–49% possible | <30% speculative

## 📊 Market snapshot
[Describe actual price movements from the market data: which assets moved, direction, magnitude. 2-3 sentences interpreting what this signals about risk appetite — risk-on vs risk-off, sector rotation, fear or greed. Be specific with numbers from the data.]

## 💸 Money flows — where money is moving RIGHT NOW

Scan ALL the news data above for items containing any of these signals:
- Funding round or contract announced
- Hiring or layoffs targeting a specific function
- Public case study with a concrete result (revenue, conversion rate, cost saved)
- Market rates or prices discussed
- Partnership where one party pays the other

For each confirmed SECTOR write a card in this exact format:

**[Sector — specific, not "AI" but "AI agents for inbound lead qualification"]**
[2-3 sentences: who is paying whom, for what exactly, and why this flow appeared right now. Example: "Mid-size tech companies and growth-stage startups are paying AI tool developers for dev automation systems and real-time agent dashboards. The trigger was the Claude Code source leak revealing massive adoption — but also creating distrust of Anthropic, pushing buyers toward independent alternatives."] Sources: [article title(s) from the data]

STRICT RULES — follow exactly:
1. Only include a sector if you found 2+ INDEPENDENT signals from DIFFERENT sources in the data above
2. If signals contradict each other — show the range and note both sources in the prose
3. If no proof in the data — do not include the sector, do not speculate
4. Sort cards: most confirming signals first, then by volume
5. Maximum 5 sectors
6. If fewer than 2 sectors pass the 2-signal rule, write: "Insufficient confirmed signals in current data period."

## 📈 Where to invest now

Based on confirmed money flows above + market snapshot, give concrete recommendations:

- **Crypto:** [BUY / HOLD / AVOID] — [reason grounded in market data + news, 1-2 sentences]
- **Stocks:** [BUY / HOLD / AVOID] — [specify sectors: tech, AI, energy, etc. + why]
- **Sector to enter now:** [pick from Money Flows above or identify a new one with clear signals] — [timing window, competition level, why now specifically]
- **What to avoid:** [asset or sector with negative signals] — [specific reason from the data]

## ✅ 3 things worth a closer look this week
[3 specific items from the data. For each: title/project name + one sentence on why it deserves attention.]

Be specific and data-driven throughout. Reference actual project names, numbers, and titles from the data. No generic statements.
"""


PREDICTIONS_PROMPT = """You are a strategic analyst. Your job is to find CAUSAL CHAINS between domains — how events in one field predict outcomes in another. You are NOT summarizing topics; you are mapping the force lines connecting them.

=== DATA STRUCTURE ===
The data below is organized by CONFIRMED THEMES (topics verified across 2+ independent organic sources) and then by single-source signals for additional context.

CONFIRMED themes = HIGH CONFIDENCE — build predictions on these.
Single-source signals = context only — use to support confirmed themes, not as standalone evidence.
Product Hunt items = company marketing — niche exists, demand NOT confirmed. A PH launch + Reddit discussion of the SAME app is ONE company's marketing on two platforms, NOT independent cross-niche confirmation.

=== NEWS & SIGNALS (last {days} days, organized by confirmed themes) ===
{news_context}

=== MARKET DATA (price movements, risk indicators) ===
{market_context}

---

INSTRUCTIONS:
- Build every prediction on a CAUSAL MECHANISM, not just topic correlation.
- Real cross-niche: GitHub trending in domain X + enterprise budget news in domain Y + consumer search spike in domain Z → prediction in domain W
- Invalid cross-niche: "AI app on Product Hunt" + "AI discussed on Reddit" = one company's promo, not a signal chain
- Be specific and falsifiable. Every prediction must be checkable on the stated date.
- Write ONLY the final report. No meta-commentary, no template text.

# 🔮 Predictions — {date}
_Based on {days}-day cross-niche signal analysis_

## 🧭 Segment movement map

One bullet per segment. ONLY include segments with CONFIRMED signals (2+ sources). Skip the rest.
Each bullet MUST be a complete sentence: who + specific action + reason from the data.
Bad: "Retail investors: switching to Anthropic stocks after Claude leak." (vague, contradictory)
Good: "Retail investors are pulling capital from Anthropic-linked assets after the Claude Code source leak damaged trust, and redirecting toward open-source AI infrastructure plays confirmed by GitHub and HN signal spikes."

- **Retail investors / everyday people:** concrete action + reason grounded in confirmed data
- **Enterprises:** where budget and attention is specifically going — cite confirmed signal
- **SMBs:** tools, pivots, or problems — cite the confirmed signal
- **Developers:** what they are building or abandoning — cite GitHub + HN signals
- **Consumers:** search or behavior shifts — cite Google Trends or Reddit
- **Micro-SaaS founders:** growing, shrinking, or pivoting — toward what exactly
- **Governments / regulators:** regulation target or funding focus — cite news signal

## 🎯 Predictions with probabilities

Write exactly 10 predictions. Mix time horizons (2 weeks / 1 month / 3 months).
Each must be specific and falsifiable — checkable on a specific date.
Each prediction must state the causal mechanism in 1 sentence (what drives it) instead of citing a section above.

**[The actual prediction — name specific company, technology, market, or measurable event]**
⏱ Horizon: [specific timeframe]
📊 Probability: X%
🔗 Signals: [2–3 confirmed items from the data — cite source + score]
⚡ Why: [1 sentence — what cross-domain dynamic drives this prediction]
⚠️ Wildcard: [one concrete event that would invalidate this prediction]

Probability scale: 90%+ near-certain | 70–89% likely | 50–69% probable | 30–49% possible | <30% speculative

## 📈 Market & investment signals

Based ONLY on confirmed cross-niche signals — not hype, not single-source speculation.
Each entry MUST name a specific asset, sector, or instrument — not vague categories.
Let the data decide the categories: could be crypto, stocks, real estate, commodities, bonds, private equity — whatever the signals point to.

**Strongest BUY signal:**
[Name the specific asset/sector/instrument — e.g. "European sovereign cloud infrastructure stocks", "Bitcoin", "open-source AI tooling startups"] — [cite 2+ independent signals] — [specific time window]

**Strongest AVOID signal:**
[Name the specific asset/sector — e.g. "Anthropic-adjacent SaaS", "centralized social platforms"] — [cite specific negative confirmed signals] — [why now specifically]

**Contrarian opportunity:**
[Something the data reveals that consensus hasn't priced in yet — name specific niche or asset]
Evidence: [name specific confirmed signals that market is ignoring]

**Cascade risk:**
[Specific event in a named sector that would negatively cascade into another named sector]
Mechanism: [how the cascade works] | Probability: X%

## 🚀 Trending niches to enter or develop

Based on the confirmed signals above — which business or technology niches are showing the strongest entry opportunity right now?
List 4–6 niches. For each: one bold name + 1-2 sentences on why the signal is strong and what direction to take.
These are NOT investment calls — these are product/startup/career bets based on where momentum is building.
Examples of how to name niches: "AI coding agents", "sovereign cloud platforms", "open-source LLM tooling", "AI engineering consulting" — whatever the data actually shows.
Only include niches confirmed by 2+ independent organic sources.

## ⚡ Highest-confidence call

3–4 sentences: your #1 prediction with the strongest multi-source signal support.
What will happen, when exactly, which SPECIFIC confirmed signals make it near-certain, what to do RIGHT NOW.
"""


def generate_briefing(days: int = 14) -> str:
    """
    Generate briefing combining top news (last N days) + market history.
    Saves report to exports/.
    """
    news_ctx = _build_briefing_context(days=days, top_per_source=60)
    if not news_ctx:
        return "⚠️ No data. Run /research first."

    from core.market_pulse import market_context_for_llm
    market_ctx = market_context_for_llm(snapshots=10)
    if not market_ctx:
        market_ctx = "No market data yet. Run /market to fetch."

    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    prompt = BRIEFING_PROMPT_V2.format(
        days=days,
        snapshots=10,
        news_context=news_ctx[:12000],
        market_context=market_ctx[:3000],
        date=date_str,
    )

    prompt = _lang_wrap(prompt)

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        from core.token_tracker import track_response
        track_response(response, "trends.briefing")
        briefing = response.content
    except Exception as e:
        from core.error_logger import log_error
        log_error("trends.briefing", "LLM call failed", str(e))
        return f"❌ Error: {e}"

    out = BRIEFING_DIR / f"briefing_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
    out.write_text(briefing, encoding="utf-8")

    return briefing


def generate_predictions(days: int = 14) -> str:
    """
    Generate cross-niche predictions with probabilities.
    Uses thematic context (confirmed cross-source clusters) instead of raw feed.
    Saves report to exports/.
    """
    # Use thematic context: pre-clustered by confirmed cross-source themes
    news_ctx = _build_thematic_context(days=days)
    if not news_ctx:
        return "⚠️ No data. Run /research first."

    from core.market_pulse import market_context_for_llm
    market_ctx = market_context_for_llm(snapshots=10)
    if not market_ctx:
        market_ctx = "No market data yet. Run /market to fetch."

    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    prompt = PREDICTIONS_PROMPT.format(
        days=days,
        news_context=news_ctx[:14000],
        market_context=market_ctx[:3000],
        date=date_str,
    )
    prompt = _lang_wrap(prompt)

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        from core.token_tracker import track_response
        track_response(response, "trends.predictions")
        result = response.content
    except Exception as e:
        from core.error_logger import log_error
        log_error("trends.predictions", "LLM call failed", str(e))
        return f"❌ Error: {e}"

    out = BRIEFING_DIR / f"predictions_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
    out.write_text(result, encoding="utf-8")

    return result


# ── Opportunity scanner ──────────────────────────────────────────────────────────

OPPORTUNITY_PROMPT = """You are a market opportunity analyst. Find concrete market niches with real entry potential based on the data below.

SIGNAL QUALITY RULES:
- A niche is CONFIRMED only if it appears in 2+ independent organic sources (HN, Reddit, GitHub, news, arXiv).
- Product Hunt launches alone are NOT confirmation — niche exists, but demand is unproven.
- A PH launch discussed on Reddit is still ONE company's marketing. That is not independent confirmation.

{context}

---

## 🎯 Market niches with real potential right now

Find 4–6 niches. For each provide:

- **Niche name** (specific — not "AI tools" but "AI-powered code review for solo developers")
- **Why it's growing:** cite the specific signals from the data — source names, titles, scores
- **Confirmed by:** list which independent sources confirm this (minimum 2 required)
- **How to enter:** product, service, or content — concrete first step
- **Competition level:** Low / Medium / High — with reasoning
- **Time window:** how long before this niche gets crowded, and why

Only include niches confirmed by real cross-source signals. Skip anything based on a single source or a Product Hunt launch alone.
"""


def scan_opportunities() -> str:
    ctx = _build_feed_context(hours=48)
    if not ctx:
        return "⚠️ No data for analysis."
    prompt = _lang_wrap(OPPORTUNITY_PROMPT.format(context=ctx[:8000]))
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        from core.token_tracker import track_response
        track_response(response, "trends.opportunities")
        return response.content
    except Exception as e:
        from core.error_logger import log_error
        log_error("trends.opportunities", "LLM call failed", str(e))
        return f"❌ Error: {e}"


# ── Feed stats ───────────────────────────────────────────────────────────────────

def feed_stats() -> dict:
    items = load_feed(limit=5000)
    if not items:
        return {"total": 0, "by_source": {}, "last_update": "never"}

    counts = {}
    last_ts = ""
    for item in items:
        s = item.get("source", "unknown")
        counts[s] = counts.get(s, 0) + 1
        ts = item.get("ts", "")
        if ts > last_ts:
            last_ts = ts

    try:
        last_dt = datetime.fromisoformat(last_ts).strftime("%d.%m.%Y %H:%M")
    except Exception:
        last_dt = last_ts

    return {"total": len(items), "by_source": counts, "last_update": last_dt}


QUICK_SUMMARY_PROMPT = """You are a personal analyst. Fresh data was just collected from multiple sources.
Below are ONLY NEW items (duplicates already filtered out).

{context}

---

Write a brief summary covering what is happening in the world right now, then highlight what matters from a builder/investor perspective.
Include a section only if there is actual data from that source. Skip sections with no data entirely (do NOT write "No data").

## 🌍 What's happening right now ({count} new items)

[For each source that has data, write 1-2 sentences about the most notable stories — general news, tech, science, business, politics, anything important:]
**📰 World News:** [top headlines from mainstream media — events, politics, economy, science]
**🔬 arXiv:** [most significant new research papers — what problems they tackle]
**🟠 Hacker News:** [most discussed topics — tech, society, tools, ideas]
**🔴 Reddit:** [what communities are reacting to — events, products, debates]
**🐙 GitHub:** [trending repos and what problem they solve]
**🔶 Product Hunt:** [notable launches]
**🐘 Mastodon:** [notable discussions]
**💻 Dev.to:** [top articles and why they matter]
**📈 Google Trends:** [what people are searching — signals of public interest]

## 🔥 The most important story right now
[Pick the single most significant item from any source. 2-3 sentences: what it is, why it matters, what it changes.]

## 💡 Signal worth acting on
[One concrete opportunity or trend from this batch — could be a niche to build in, a technology to learn, or a shift to position for. 2-3 sentences.]

## ⚡ 3 items worth a closer look
[3 specific titles from the new data — each with one line on why it matters.]

CRITICAL OUTPUT RULE: Every sentence must be complete and unambiguous. Always state WHO + does WHAT precisely.
Bad: "AI companies take 60% more depending on language." Good: "AI companies charge 60% more for the same prompts from non-English users due to BPE tokenization inefficiency."
Bad: "People are moving away from platforms." Good: "Developers are migrating from centralized CI services to self-hosted alternatives after a series of account lockdowns."
If a fact would confuse the reader without context, include that context in the same sentence.

Be concise. No filler. Only what's actually in the data.
"""


MONEY_FLOWS_PROMPT = """You are a financial intelligence analyst. Your job is to identify sectors where money is ACTUALLY moving right now — not trends, not speculation, only confirmed transactions backed by evidence from the data below.

=== NEWS & SIGNALS (last {days} days, ranked by engagement and impact) ===
{news_context}

---

Scan the data above for items containing any of these signals:
- Funding round or contract announced
- Hiring or layoffs targeting a specific function
- Public case study with a concrete result (revenue, conversion rate, cost saved)
- Market rates or prices discussed in context of a purchase decision
- Partnership where one party pays the other

For each confirmed SECTOR write a card:

**[Sector — be specific: not "AI" but "AI agents for inbound lead qualification"]**
[2-3 sentences: who is paying whom, for what exactly, and why this flow appeared right now. If volume is stated in the source, include it. Example: "Mid-size tech companies and growth-stage startups are paying AI tool developers for dev automation systems and real-time agent dashboards. The trigger was the Claude Code source leak revealing massive adoption — but also creating distrust of Anthropic, pushing buyers toward independent alternatives."] Sources: [article title(s) from the data]

STRICT RULES:
1. Only include a sector confirmed by 2+ INDEPENDENT signals from DIFFERENT sources
2. If signals contradict — note the range in the prose and cite both sources
3. No proof = not included. No speculation.
4. Sort by: number of confirming signals first, then by volume
5. Maximum 7 sectors. Minimum 0 — only include what is actually confirmed.
6. After the cards: write a 2-3 sentence conclusion on which sector has the strongest and most urgent signal overall, and why.

If fewer than 2 sectors pass the 2-signal rule, write only:
"Insufficient confirmed signals in current data period. Collect more data with /research and retry."

Write ONLY the final report. No meta-commentary, no template text.

# 💸 Money Flows — {date}
_Period: last {days} days | Only sectors with 2+ confirmed signals_
"""


def generate_money_flows(days: int = 14) -> str:
    """
    Standalone money flows report: sectors where money is confirmed moving.
    Saves report to exports/.
    """
    news_ctx = _build_briefing_context(days=days, top_per_source=60)
    if not news_ctx:
        return "⚠️ No data. Run /research first."

    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    prompt = MONEY_FLOWS_PROMPT.format(
        days=days,
        news_context=news_ctx[:14000],
        date=date_str,
    )
    prompt = _lang_wrap(prompt)

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        from core.token_tracker import track_response
        track_response(response, "trends.money_flows")
        result = response.content
    except Exception as e:
        from core.error_logger import log_error
        log_error("trends.money_flows", "LLM call failed", str(e))
        return f"❌ Error: {e}"

    out = BRIEFING_DIR / f"money_flows_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
    out.write_text(result, encoding="utf-8")

    return result


def quick_summary_from_new(new_items: list) -> str:
    """Generate a mini-report specifically from freshly collected (non-duplicate) items."""
    if not new_items:
        return "📭 No new items found — everything was already in the database."

    # Build context from new items only
    sections: Dict[str, List[str]] = {}
    for item in new_items:
        source = item.get("source", "other")
        title  = item.get("title", "")
        desc   = item.get("description") or item.get("selftext") or ""
        score  = item.get("score") or item.get("stars") or ""
        line   = f"• {title}"
        if desc:
            line += f" — {desc[:100]}"
        if score:
            line += f" [{score}]"
        sections.setdefault(source, []).append(line)

    src_labels = {
        "hackernews":      "HACKER NEWS",
        "reddit":          "REDDIT",
        "github_trending": "GITHUB TRENDING",
        "producthunt":     "PRODUCT HUNT",
        "mastodon":        "MASTODON",
        "devto":           "DEV.TO",
        "google_trends":   "GOOGLE TRENDS",
        "newsapi":         "NEWS (WORLD)",
        "arxiv":           "ARXIV PAPERS",
    }
    parts = []
    for src, lines in sections.items():
        label = src_labels.get(src, src.upper())
        parts.append(f"=== {label} ({len(lines)} new) ===\n" + "\n".join(lines[:25]))

    context = "\n\n".join(parts)
    prompt  = _lang_wrap(QUICK_SUMMARY_PROMPT.format(context=context[:7000], count=len(new_items)))

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        from core.token_tracker import track_response
        track_response(response, "trends.quick_summary")
        return response.content
    except Exception as e:
        from core.error_logger import log_error
        log_error("trends.quick_summary", "LLM call failed", str(e))
        return f"❌ Summary generation error: {e}"
