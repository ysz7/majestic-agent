"""/briefing [days] — deep intelligence briefing from stored news corpus."""

from majestic.cli.commands.context import CommandContext
from majestic.cli.commands.registry import command
from majestic.intelligence import llm_with_retry, load_recent_briefing


@command("/briefing")
async def handle(ctx: CommandContext):
    import re
    import time
    from datetime import date
    from majestic import display as _display

    words = ctx.text.strip().split()
    days = 30
    if len(words) > 1:
        try:
            days = int(words[1])
        except ValueError:
            pass

    if ctx.settings is None:
        ctx.out("[red]No settings — briefing requires a profile.[/red]")
        return True

    try:
        db = ctx.backend.research()
        articles = db.get_articles(days=days)
        stats = db.stats()
        db.close()
    except Exception as e:
        ctx.out(f"[red]DB error: {e}[/red]")
        return True

    if not articles:
        ctx.out(f"[dim]No articles in database for the last {days} days. Run /research first.[/dim]")
        return True

    from majestic.tools.research.corpus import build_corpus, calc_article_budget
    _ctx_lim = getattr(ctx.runtime.llm, "context_limit", 128_000)
    _art_budget = calc_article_budget(_ctx_lim)
    if _ctx_lim < 16_000:
        from majestic.tools.research.summarizer import build_corpus_summarized
        corpus_lines, capped = await build_corpus_summarized(articles, ctx.runtime.llm, _art_budget)
    else:
        corpus_lines, capped = build_corpus(articles, token_budget=_art_budget, include_summaries=True)

    _prices: list[dict] = []
    _prices_ts = ""
    try:
        db2 = ctx.backend.research()
        _prices, _prices_ts = db2.get_latest_prices()
        db2.close()
    except Exception:
        pass

    _display.tree_reset()
    _display.tree_step("Research DB", f"{stats['total']} total · last {days}d: {len(articles)} articles")
    if _prices:
        _display.tree_step("Prices", f"{len(_prices)} assets · {_prices_ts[:16]}")

    count_note = f"{len(articles)} articles" + (" (truncated)" if capped else "")
    lines = [f"INTELLIGENCE CORPUS -- {count_note}, last {days} days\n"]

    if _prices:
        from majestic.tools.research.prices import format_prices_for_corpus as _fmt
        _pb = _fmt(_prices, _prices_ts)
        if _pb:
            lines.append(_pb)

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

    _lang = getattr(ctx.settings, "agent_language", "") or "en"
    _is_non_en = _lang and _lang.lower() not in ("en", "english")
    _lang_rule = (
        f"LANGUAGE: Write the ENTIRE response in {_lang}, including all section headings. "
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

    t0 = time.monotonic()
    try:
        with _display.TreePending("analyzing..."):
            _resp = await llm_with_retry(ctx.runtime.llm, _messages, step_type="reason")
        _display.tree_close()
        result = _resp.get("content", "")
        _in = _resp.get("input_tokens", 0)
        _out = _resp.get("output_tokens", 0)
        ctx.runtime._tokens_used = _in + _out
        _cost = _resp.get("cost") or 0.0
        if not _cost and (_in or _out):
            try:
                from majestic.llm.base import BaseLLM
                _cost = BaseLLM._estimate_cost(_in, _out)
            except Exception:
                pass
        ctx.runtime._cost_used = _cost
    except Exception as exc:
        _display.tree_close("error")
        result = f"Error: {exc}"
        _cost = 0.0
    elapsed = time.monotonic() - t0

    m = re.search(r'^##', result, re.MULTILINE)
    if m:
        result = result[m.start():]

    try:
        bd = ctx.settings.workspace_dir / "briefings"
        bd.mkdir(parents=True, exist_ok=True)
        fn = bd / f"{date.today().isoformat()}.md"
        fn.write_text(result, encoding="utf-8")
        _display.tree_reset()
        _display.tree_step("saved", fn.name)
        _display.tree_close()
    except Exception:
        pass

    if ctx.channel is not None:
        await ctx.channel.send(f"\n{result}\n")
    else:
        ctx.out(result)

    from majestic import display as _d
    _d.inline_stats(
        tokens=getattr(ctx.runtime, "_tokens_used", 0),
        cost=getattr(ctx.runtime, "_cost_used", 0.0),
        elapsed=elapsed,
    )
    return True
