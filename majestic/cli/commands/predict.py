"""/predict [days] — probabilistic forecasts grounded in live market data."""

import re
import time
from collections import defaultdict
from datetime import date

from majestic.cli.commands.context import CommandContext
from majestic.cli.commands.registry import command
from majestic.core.intelligence import llm_with_retry, load_recent_briefing


@command("/predict")
async def handle(ctx: CommandContext):
    from majestic import display as _display

    words = ctx.text.strip().split()
    days = 30
    if len(words) > 1:
        try:
            days = int(words[1])
        except ValueError:
            pass

    if ctx.settings is None:
        ctx.out("[red]No settings -- /predict requires a profile.[/red]")
        return True

    articles: list[dict] = []
    try:
        db = ctx.backend.research()
        articles = db.get_articles(days=days)
        db.close()
    except Exception:
        pass

    pains: list[dict] = []
    try:
        db2 = ctx.backend.pains()
        pains = db2.get_pains(days=days)
        db2.close()
    except Exception:
        pass

    if not articles and not pains:
        ctx.out(f"[dim]No data for the last {days} days. Run /research and /pains first.[/dim]")
        return True

    briefing = load_recent_briefing(ctx.settings, max_days=3)
    prices: list[dict] = []
    prices_ts = ""
    try:
        db3 = ctx.backend.research()
        prices, prices_ts = db3.get_latest_prices()
        db3.close()
    except Exception:
        pass

    _display.tree_reset()
    if briefing:
        _display.tree_step("Briefing", "macro context loaded")
    if prices:
        _display.tree_step("Prices", f"{len(prices)} assets · {prices_ts[:16]}")
    if articles:
        _display.tree_step("Research DB", f"{len(articles)} articles")
    if pains:
        _display.tree_step("Pains DB", f"{len(pains)} pain points")

    historical: list[dict] = []
    try:
        ls = ctx.backend.lessons()
        kws: set[str] = set()
        for a in (articles or [])[:15]:
            for w in re.sub(r"[^\w\s]", " ", a.get("title", "")).split():
                if len(w) > 4:
                    kws.add(w.lower())
        kw_q = " ".join(list(kws)[:15])
        if kw_q:
            historical = ls.search_signal_patterns(kw_q, limit=3)
        ls._conn.close()
    except Exception:
        pass
    if historical:
        _display.tree_step("Patterns", f"{len(historical)} historical matches")

    corpus: list[str] = [f"INTELLIGENCE CORPUS -- last {days} days\n"]

    if prices:
        from majestic.tools.research.prices import format_prices_for_corpus as _fmt
        pb = _fmt(prices, prices_ts)
        if pb:
            corpus.append(pb)

    if briefing:
        b_cap = briefing[:8_000] + ("\n[... truncated ...]" if len(briefing) > 8_000 else "")
        corpus.append("=== MACRO SYNTHESIS (from /briefing) ===\n")
        corpus.append(b_cap)
        corpus.append("")

    if articles:
        from majestic.tools.research.corpus import build_corpus as _bc, calc_article_budget as _cab
        ctx_lim = getattr(ctx.runtime.llm, "context_limit", 128_000)
        bgt = _cab(ctx_lim, section_fraction=0.45)
        if ctx_lim < 16_000:
            from majestic.tools.research.summarizer import build_corpus_summarized as _bcs
            news_lines, _ = await _bcs(articles, ctx.runtime.llm, bgt)
        else:
            news_lines, _ = _bc(articles, token_budget=bgt, include_summaries=True)
        corpus.append(f"=== NEWS & MARKET SIGNALS ({len(articles)} articles) ===\n")
        corpus.extend(news_lines)

    if pains:
        by_dom: dict = defaultdict(list)
        for p in pains:
            by_dom[p.get("domain", "other")].append(p)
        corpus.append(f"=== DEMAND & PAIN SIGNALS ({len(pains)} pain points) ===\n")
        pc = 0
        for dom, items in sorted(by_dom.items(), key=lambda x: -len(x[1])):
            corpus.append(f"[{dom.upper()} -- {len(items)} mentions]")
            for p in items[:15]:
                e = f"· [{p.get('source','')}] {p.get('pain_text','')}"
                corpus.append(e)
                pc += len(e)
                if pc >= 15_000:
                    break
            corpus.append("")
            if pc >= 15_000:
                break

    if historical:
        corpus.append("=== HISTORICAL SIGNAL PATTERNS ===")
        corpus.append("[Previously observed combinations -- use to calibrate probabilities]\n")
        for hp in historical:
            sig = hp.get("signals_text", "").replace("\n", " · ")[:220]
            summ = hp.get("prediction_summary", "")[:350]
            conf = f"{hp.get('avg_confidence', 0.0):.0f}%"
            dt = hp.get("created_at", "")[:10]
            corpus.append(f"[{dt}] avg confidence={conf}")
            corpus.append(f"Signals: {sig}")
            corpus.append(f"Prior predictions: {summ}")
            corpus.append("")

    instructions = (
        "CRITICAL: Every prediction in SECTIONS 2-4 MUST be grounded in signals from at least 2 "
        "DIFFERENT corpus sections. Single-source observations belong ONLY in SECTION 5.\n\n"
        "## EXECUTIVE SUMMARY\n\n"
        "Write FIRST. 2 sentences max: (1) highest-confidence prediction + probability; "
        "(2) signal combination that drives it.\n\n---\n\n"
        "## SECTION 1 -- SIGNAL MAP\n\n"
        "8-12 directional forces. Group signals pointing the same way.\n"
        "**-> [DIRECTION]** (N signals)\n- [Signal]: (source, date)\n"
        "- Cross-domain: which other sectors does this reach?\n\n---\n\n"
        "## SECTION 2 -- SHORT-TERM (1-4 weeks)\n\n"
        "**[PREDICTION]** -- **XX%**\n"
        "- Causal chain: [A] -> [mechanism] -> [B] -> outcome\n"
        "- Cross-domain ripple · Base rate · Counter-signals · Invalidation · Winners/Losers\n\n"
        "3-5 predictions, highest -> lowest.\n\n---\n\n"
        "## SECTION 3 -- MEDIUM-TERM (1-3 months)\n\nSame format. 3-5 predictions.\n\n---\n\n"
        "## SECTION 4 -- LONG-TERM (6-12 months)\n\nSame format. 2-4 predictions.\n\n---\n\n"
        "## SECTION 5 -- TAIL RISKS\n\n"
        "2-3 events under 20% probability but catastrophic impact.\n"
        "**[RISK]** -- **XX%** · Weak signal · Impact · Early warning\n\n"
        "---\nEnd: highest-confidence prediction and the exact signal combination."
    )

    _lang = getattr(ctx.settings, "agent_language", "") or "en"
    _is_non_en = _lang and _lang.lower() not in ("en", "english")
    _lang_rule = (
        f"LANGUAGE: Write the ENTIRE response in {_lang}, including all section headings. "
        "Source/article titles may remain in their original language. "
    ) if _is_non_en else ""
    _system = (
        f"{_lang_rule}"
        "You are a professional intelligence analyst trained in Superforecasting methodology. "
        "Your task is SYNTHESIS -- find patterns from MULTIPLE independent signals. "
        "Your response MUST begin with a '##' section header -- nothing before it. "
        "No preamble. No meta-commentary. Calibrated probabilities only."
    )
    _prompt = "\n".join(corpus) + "\n" + instructions
    _messages = [
        {"role": "system", "content": _system},
        {"role": "user",   "content": _prompt},
    ]

    t0 = time.monotonic()
    try:
        with _display.TreePending("analyzing signals..."):
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
        pred_dir = ctx.settings.workspace_dir / "predictions"
        pred_dir.mkdir(parents=True, exist_ok=True)
        fn = pred_dir / f"{date.today().isoformat()}.md"
        fn.write_text(result, encoding="utf-8")
        _display.tree_reset()
        _display.tree_step("saved", fn.name)

        if result and not result.startswith("Error:"):
            sig_names = [s.strip().rstrip("(").strip()
                         for s in re.findall(r'\*\*->\s*([^*\n(]+)', result)][:12]
            conf_vals = [int(c) for c in re.findall(r'\*\*(\d+)%\*\*', result)]
            avg_conf = sum(conf_vals[:8]) / len(conf_vals[:8]) if conf_vals else 0.0
            sec2 = re.search(r'^## SECTION 2', result, re.MULTILINE)
            pred_sum = (result[sec2.start():sec2.start() + 600] if sec2 else result[:600])
            if sig_names:
                ls_save = ctx.backend.lessons()
                ls_save.save_signal_pattern(sig_names, pred_sum, avg_conf)
                ls_save._conn.close()
                _display.tree_step("patterns", f"{len(sig_names)} signals -> memory")
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
