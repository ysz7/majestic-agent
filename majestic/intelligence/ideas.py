"""Ideas service — synthesize business opportunities from the intelligence
corpus (pains + research + briefing + ProductHunt launches + past ideas).

The pure corpus-building + prompt + LLM call lives here (reusable, testable);
the CLI handler keeps only data-fetch, display, and persistence. Logic moved
verbatim from the former fat handler (Phase K.6).
"""

from __future__ import annotations

import re
from collections import defaultdict

from majestic.intelligence.llm import llm_with_retry


async def generate_ideas(
    *,
    llm,
    pains: list[dict],
    articles: list[dict] | None = None,
    briefing: str = "",
    past_ideas: list[dict] | None = None,
    days: int = 30,
    lang: str = "en",
) -> dict:
    """Generate ranked business ideas. Returns ``{markdown, tokens, cost}``."""
    articles = articles or []
    past_ideas = past_ideas or []

    launches = [a for a in articles if a.get("category") == "launches"]
    news = [a for a in articles if a.get("category") != "launches"]

    high_demand = [p for p in pains if p.get("intensity") == "HIGH" or p.get("willingness_to_pay")]
    regular = [p for p in pains if not (p.get("intensity") == "HIGH" or p.get("willingness_to_pay"))]

    corpus: list[str] = [f"INTELLIGENCE CORPUS -- last {days} days\n"]

    if briefing:
        b_cap = briefing[:8_000] + ("\n[... truncated ...]" if len(briefing) > 8_000 else "")
        corpus.append("=== MACRO INTELLIGENCE (from /briefing) ===\n")
        corpus.append(b_cap)
        corpus.append("")

    if high_demand:
        corpus.append(f"=== HIGH DEMAND SIGNALS ({len(high_demand)} pain points) ===\n"
                      "[Strongest demand -- HIGH intensity or willingness to pay]\n")
        hd_chars = 0
        for p in high_demand[:60]:
            src = f"[{p.get('source', '')}] " if p.get("source") else ""
            wtp = " WTP" if p.get("willingness_to_pay") else ""
            entry = f"· {src}[{p.get('intensity','H')}] {p.get('pain_text', '')}{wtp}"
            corpus.append(entry)
            hd_chars += len(entry)
            if hd_chars >= 15_000:
                break
        corpus.append("")

    by_dom: dict = defaultdict(list)
    for p in regular:
        by_dom[p.get("domain", "other")].append(p)
    if by_dom:
        corpus.append(f"=== DEMAND & PAIN SIGNALS ({len(regular)} additional pain points) ===\n")
        rp_chars = 0
        for dom, items in sorted(by_dom.items(), key=lambda x: -len(x[1])):
            corpus.append(f"[{dom.upper()} -- {len(items)} mentions]")
            for p in items[:20]:
                e = f"· [{p.get('source', '')}] {p.get('pain_text', '')}"
                corpus.append(e)
                rp_chars += len(e)
                if rp_chars >= 15_000:
                    break
            corpus.append("")
            if rp_chars >= 15_000:
                break

    if past_ideas:
        corpus.append("=== PAST IDEAS (do NOT repeat -- find NEW angles) ===\n")
        for pi in past_ideas:
            corpus.append(f"· {pi.get('lesson', '')[:300]}")
        corpus.append("")

    if news:
        from majestic.tools.research.corpus import build_corpus as _bc, calc_article_budget as _cab
        ctx_lim = getattr(llm, "context_limit", 128_000)
        bgt = _cab(ctx_lim, section_fraction=0.35)
        if ctx_lim < 16_000:
            from majestic.tools.research.summarizer import build_corpus_summarized as _bcs
            news_lines, _ = await _bcs(news, llm, bgt)
        else:
            news_lines, _ = _bc(news, token_budget=bgt, include_summaries=True)
        corpus.append(f"=== MARKET & NEWS SIGNALS ({len(news)} articles) ===\n")
        corpus.extend(news_lines)

    if launches:
        corpus.append(f"=== MARKET LAUNCHES -- {len(launches)} products on ProductHunt ===\n"
                      "Use to assess competition: gap or already built?\n")
        for l in launches[:30]:
            corpus.append(f"· [{l.get('date','')}] {l.get('title','')}")
            if l.get("summary"):
                corpus.append(f"  {l.get('summary','')[:200]}")
        corpus.append("")

    _is_non_en = lang and lang.lower() not in ("en", "english")
    _lang_rule = (
        f"LANGUAGE: Write the ENTIRE response in {lang}, including all section headings. "
        "Source/article titles may remain in their original language. "
    ) if _is_non_en else ""

    instructions = (
        "TASK: Identify 7 realistic business opportunities by synthesizing ALL FOUR corpus layers.\n"
        "PRIORITY: Ideas backed by HIGH DEMAND signals rank higher.\n"
        "RULE: Every idea must connect at least 2 layers.\n\n"
        "## TOP OPPORTUNITY\n\n"
        "Write this FIRST. 2 sentences: (1) the single strongest idea; (2) the HIGH DEMAND pain + market signal.\n\n"
        "---\n\n"
        "## SECTION 1 -- BOTTLENECK MAP\n\n"
        "5-7 structural gaps where demand exists but supply hasn't caught up.\n\n"
        "**-> [GAP NAME]** -- [one sentence: what's missing and why it matters now]\n"
        "- Demand: (cite specific pain + intensity)\n"
        "- Competition: already built / partial / open field\n\n"
        "---\n\n"
        "## SECTION 2 -- 7 IDEAS\n\n"
        "Rank #1 highest conviction -> #7 lowest.\n\n"
        "**#N -- [Product Name]** *([who it's for])*\n\n"
        "**Core**: [2-3 sentences: what it is and why]\n"
        "**How it works**: [specific scenario from user's perspective]\n"
        "**Demand**: [specific pains from corpus + intensity + WTP signal]\n"
        "**Why now**: [what changed recently -- cite corpus]\n"
        "**For whom**: [primary user + second-order beneficiaries]\n"
        "**Revenue**: [monetization + any WTP signals]\n"
        "**Competition**: [what exists on PH/market -> specific gap]\n"
        "**Kill check**: [what must be true in 30 days or idea is dead]\n"
        "**Conviction**: XX%\n\n"
        "No filler. If fewer than 7 strong gaps exist -- say so."
    )

    _system = (
        f"{_lang_rule}"
        "You are a world-class product strategist and venture analyst. "
        "Your response MUST begin with a '##' section header -- nothing before it. "
        "No preamble. No meta-commentary."
    )
    _prompt = "\n".join(corpus) + "\n\n" + instructions
    _messages = [
        {"role": "system", "content": _system},
        {"role": "user",   "content": _prompt},
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

    return {"markdown": result, "tokens": _in + _out, "cost": cost}
