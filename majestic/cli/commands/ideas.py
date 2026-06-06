"""/ideas [days] — generate startup ideas from the accumulated pains corpus."""

import re
import time
from collections import Counter, defaultdict
from datetime import date

from majestic.cli.commands.context import CommandContext
from majestic.cli.commands.registry import command
from majestic.intelligence import llm_with_retry, load_recent_briefing


@command("/ideas")
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
        ctx.out("[red]No settings -- /ideas requires a profile.[/red]")
        return True

    try:
        db = ctx.backend.pains()
        pains_all = db.get_pains(days=days)
        db.close()
    except Exception as e:
        ctx.out(f"[red]Pains DB error: {e}[/red]")
        return True

    if not pains_all:
        ctx.out(f"[dim]No pain points for the last {days} days. Run /pains first.[/dim]")
        return True

    articles: list[dict] = []
    try:
        db2 = ctx.backend.research()
        articles = db2.get_articles(days=days)
        db2.close()
    except Exception:
        pass

    briefing = load_recent_briefing(ctx.settings, max_days=3)
    launches = [a for a in articles if a.get("category") == "launches"]
    news     = [a for a in articles if a.get("category") != "launches"]

    high_demand = [p for p in pains_all if p.get("intensity") == "HIGH" or p.get("willingness_to_pay")]
    regular     = [p for p in pains_all if not (p.get("intensity") == "HIGH" or p.get("willingness_to_pay"))]

    past_ideas: list[dict] = []
    try:
        ls = ctx.backend.lessons()
        dom_kw = " ".join([d for d, _ in Counter(
            p.get("domain", "") for p in pains_all
            if p.get("domain") and p.get("domain") != "other"
        ).most_common(6)])
        if dom_kw.strip():
            past_ideas = [l for l in ls.search(dom_kw, limit=8) if l.get("task_type") == "ideas"][:3]
        ls._conn.close()
    except Exception:
        pass

    _display.tree_reset()
    if briefing:
        _display.tree_step("Briefing", "macro context loaded")
    else:
        _display.tree_step("Briefing", "not found -- run /briefing for richer analysis", status="warn")
    _hd_tag = f" · {len(high_demand)} HIGH/WTP" if high_demand else ""
    _display.tree_step("Pains DB", f"{len(pains_all)} pain points{_hd_tag} · last {days}d")
    if past_ideas:
        _display.tree_step("Memory", f"{len(past_ideas)} past idea patterns recalled")
    if news:
        _display.tree_step("Research DB", f"{len(news)} articles")
    if launches:
        _display.tree_step("ProductHunt", f"{len(launches)} launches")
    else:
        _display.tree_step("ProductHunt", "no launches -- run /research to fetch", status="warn")

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
        ctx_lim = getattr(ctx.runtime.llm, "context_limit", 128_000)
        bgt = _cab(ctx_lim, section_fraction=0.35)
        if ctx_lim < 16_000:
            from majestic.tools.research.summarizer import build_corpus_summarized as _bcs
            news_lines, _ = await _bcs(news, ctx.runtime.llm, bgt)
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

    _lang = getattr(ctx.settings, "agent_language", "") or "en"
    _is_non_en = _lang and _lang.lower() not in ("en", "english")
    _lang_rule = (
        f"LANGUAGE: Write the ENTIRE response in {_lang}, including all section headings. "
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

    t0 = time.monotonic()
    try:
        with _display.TreePending("generating ideas..."):
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
        ideas_dir = ctx.settings.workspace_dir / "ideas"
        ideas_dir.mkdir(parents=True, exist_ok=True)
        fn = ideas_dir / f"{date.today().isoformat()}.md"
        fn.write_text(result, encoding="utf-8")
        _display.tree_reset()
        _display.tree_step("saved", fn.name)

        if result and not result.startswith("Error:"):
            matches = list(re.finditer(r'\*\*#([123])\s*[--]\s*([^\*\n(]+)', result))[:3]
            if matches:
                try:
                    ls_save = ctx.backend.lessons()
                    for ms in matches:
                        istart = ms.start()
                        inext = re.search(r'\*\*#[234]|\n##', result[istart + 5:])
                        iend = (istart + 5 + inext.start() if inext else min(istart + 700, len(result)))
                        block = result[istart:iend].strip()
                        if block:
                            ls_save.save(task_type="ideas", lesson=block[:600])
                    ls_save._conn.close()
                    _display.tree_step("memory", f"{len(matches)} ideas saved to lessons")
                except Exception:
                    pass
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
