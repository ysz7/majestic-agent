"""Briefing — generation service + recent-briefing loader.

The pure corpus + prompt + LLM call lives here (reusable, testable); the CLI
handler keeps only data-fetch, display, and persistence. Logic moved verbatim
from the former fat handler (Phase K.6).
"""

from __future__ import annotations

import re

from majestic.intelligence.llm import llm_with_retry


async def generate_briefing(
    *,
    llm,
    articles: list[dict],
    prices_block: str = "",
    days: int = 30,
    lang: str = "en",
) -> dict:
    """Generate the 4-section intelligence briefing. Returns ``{markdown, tokens, cost, capped}``."""
    from majestic.tools.research.corpus import build_corpus, calc_article_budget

    ctx_lim = getattr(llm, "context_limit", 128_000)
    art_budget = calc_article_budget(ctx_lim)
    if ctx_lim < 16_000:
        from majestic.tools.research.summarizer import build_corpus_summarized
        corpus_lines, capped = await build_corpus_summarized(articles, llm, art_budget)
    else:
        corpus_lines, capped = build_corpus(articles, token_budget=art_budget, include_summaries=True)

    count_note = f"{len(articles)} articles" + (" (truncated)" if capped else "")
    lines = [f"INTELLIGENCE CORPUS -- {count_note}, last {days} days\n"]
    if prices_block:
        lines.append(prices_block)
    lines.extend(corpus_lines)

    instructions = (
        "Produce the 4-section intelligence briefing below. "
        "Rules: (1) use ONLY facts from the corpus above; (2) cite source + date for every claim; "
        "(3) actors/themes appearing in multiple categories are strongest signals.\n\n"
        "## SECTION 1 -- WORLD PICTURE\n\n"
        "Write a macro synthesis -- NOT a list of headlines. Identify 3-4 underlying structural forces "
        "that explain MOST of what you see across ALL categories together. Connect geopolitics, technology, "
        "economy, and society into one coherent narrative. Ground every claim in specific evidence.\n\n"
        "---\n\n"
        "## SECTION 2 -- MONEY FLOWS\n\n"
        "Map where capital is moving. For each significant flow:\n\n"
        "**ENTERING [sector]**\n- Actor, Evidence (source, date), Scale\n\n"
        "**LEAVING [sector]**\n- Actor, why exiting, Evidence\n\n"
        "Market signals: **BUY/HOLD/SELL/AVOID [asset]** -- evidence: (source). "
        "Cover equities, crypto, commodities, bonds -- only where corpus gives a signal.\n\n"
        "---\n\n"
        "## SECTION 3 -- PREDICTIONS & PROBABILITIES\n\n"
        "Calibration: 1 signal=30-50%, 2 independent=50-65%, 3=65-80%, 4+=80-88% max.\n\n"
        "**[EVENT STATEMENT]** -- **XX%**\n"
        "- Horizon: near-term/medium/long-term\n"
        "- Signals: (source, date) · Winners/Losers · Invalidation\n\n"
        "Generate 5-7 predictions, highest to lowest probability.\n\n"
        "---\n\n"
        "## SECTION 4 -- TOP 3 HIGH-CONVICTION IDEAS\n\n"
        "**#N -- [IDEA NAME]** -- [one-sentence concept]\n\n"
        "- News trigger, Timing uniqueness, Market signal, Key risk, Kill check, Success %\n\n"
        "Rank #1 highest -> #3 lowest.\n\n"
        "---\n\nEnd with one sentence: the single most underappreciated insight."
    )
    lines.append(instructions)
    prompt = "\n".join(lines)

    _is_non_en = lang and lang.lower() not in ("en", "english")
    _lang_rule = (
        f"LANGUAGE: Write the ENTIRE response in {lang}, including all section headings. "
        "Source/article titles may remain in their original language. "
    ) if _is_non_en else ""
    _system = (
        f"{_lang_rule}"
        "You are a world-class intelligence analyst. "
        "Your response MUST begin with a '##' section header -- nothing before it. "
        "No preamble. No meta-commentary. Cite (source, date) for every claim."
    )
    _messages = [
        {"role": "system", "content": _system},
        {"role": "user",   "content": prompt},
    ]

    resp = await llm_with_retry(llm, _messages, step_type="reason")
    result = resp.get("content", "")
    _in = resp.get("input_tokens", 0)
    _out = resp.get("output_tokens", 0)
    cost = resp.get("cost") or 0.0
    if not cost and (_in or _out):
        try:
            from majestic.llm.base import BaseLLM
            cost = BaseLLM._estimate_cost(_in, _out)
        except Exception:
            pass

    m = re.search(r'^##', result, re.MULTILINE)
    if m:
        result = result[m.start():]

    return {"markdown": result, "tokens": _in + _out, "cost": cost, "capped": capped}


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
