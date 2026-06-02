"""/ask <question> — answer a question against the accumulated intelligence corpus."""

import re
import time

from majestic.cli.commands.context import CommandContext
from majestic.cli.commands.registry import command
from majestic.core.intelligence import llm_with_retry, load_recent_briefing


@command("/ask")
async def handle(ctx: CommandContext):
    from majestic import display as _display

    question = ctx.text.strip()[len("/ask"):].strip()
    if not question:
        ctx.out("[dim]Usage: /ask <question>  e.g.: /ask how will falling oil prices affect Bitcoin?[/dim]")
        return True

    if ctx.settings is None:
        ctx.out("[red]No settings -- /ask requires a profile.[/red]")
        return True

    _display.tree_reset()

    briefing = load_recent_briefing(ctx.settings, max_days=3)
    if briefing:
        _display.tree_step("Briefing", "macro context loaded")

    prediction: str | None = None
    try:
        from datetime import date, timedelta
        pd = ctx.settings.workspace_dir / "predictions"
        if pd.exists():
            today = date.today()
            for delta in range(4):
                f = pd / f"{(today - timedelta(days=delta)).isoformat()}.md"
                if f.exists():
                    c = f.read_text(encoding="utf-8").strip()
                    if c:
                        prediction = c
                        break
    except Exception:
        pass
    if prediction:
        _display.tree_step("Predictions", "context loaded")

    kw = [w.lower() for w in re.sub(r"[^\w\s]", " ", question).split() if len(w) > 3]

    sem_results: list[dict] = []
    if ctx.semantic is not None:
        try:
            safe_q = " ".join(re.sub(r"[^\w\s]", " ", question).split()[:10])
            if safe_q.strip():
                sem_results = ctx.semantic.search(safe_q, limit=25)
            _display.tree_step("Semantic", f"{len(sem_results)} relevant chunks")
        except Exception:
            pass

    ask_articles: list[dict] = []
    try:
        db = ctx.backend.research()
        all_art = db.get_articles(days=60)
        db.close()
        if kw:
            for a in all_art:
                txt = f"{a.get('title','')} {a.get('summary','')}".lower()
                if any(k in txt for k in kw):
                    ask_articles.append(a)
        if ask_articles:
            _display.tree_step("Research DB", f"{len(ask_articles)} matching articles")
    except Exception:
        pass

    ask_pains: list[dict] = []
    try:
        db2 = ctx.backend.pains()
        all_pains = db2.get_pains(days=60)
        db2.close()
        if kw:
            for p in all_pains:
                if any(k in p.get("pain_text", "").lower() for k in kw):
                    ask_pains.append(p)
        if ask_pains:
            _display.tree_step("Pains DB", f"{len(ask_pains)} matching signals")
    except Exception:
        pass

    if not any([briefing, prediction, sem_results, ask_articles, ask_pains]):
        ctx.out("[dim]No context found. Run /research, /pains, /briefing, /predict first.[/dim]")
        return True

    corpus: list[str] = [f"ANALYSIS CORPUS -- question: {question}\n"]

    if briefing:
        corpus.append("=== MACRO INTELLIGENCE (recent /briefing) ===\n")
        corpus.append(briefing[:5_000] + ("\n[... truncated ...]" if len(briefing) > 5_000 else ""))
        corpus.append("")

    if prediction:
        corpus.append("=== PREDICTIONS (recent /predict) ===\n")
        corpus.append(prediction[:5_000] + ("\n[... truncated ...]" if len(prediction) > 5_000 else ""))
        corpus.append("")

    if sem_results:
        corpus.append(f"=== SEMANTIC HITS ({len(sem_results)}) ===\n")
        for sr in sem_results:
            corpus.append(f"[{sr.get('source','')}]: {sr.get('content','')[:300]}")
        corpus.append("")

    if ask_articles:
        corpus.append(f"=== MATCHING ARTICLES ({len(ask_articles)}) ===\n")
        for a in ask_articles[:30]:
            corpus.append(f"· [{a.get('date','')}] {a.get('source','')}: {a.get('title','')}")
            if a.get("summary"):
                corpus.append(f"  {a.get('summary','')[:200]}")
        corpus.append("")

    if ask_pains:
        corpus.append(f"=== MATCHING PAIN SIGNALS ({len(ask_pains)}) ===\n")
        for p in ask_pains[:15]:
            corpus.append(f"· [{p.get('source','')}] {p.get('pain_text','')}")
        corpus.append("")

    _lang = getattr(ctx.settings, "agent_language", "") or "en"
    _is_non_en = _lang and _lang.lower() not in ("en", "english")
    _lang_rule = (
        f"LANGUAGE: Write the ENTIRE response in {_lang}, including section headings. "
        "Source/article titles may remain in their original language. "
    ) if _is_non_en else ""

    _instructions = (
        f"QUESTION: {question}\n\n"
        "Answer using ONLY the corpus above. Format:\n\n"
        "## Direct Answer\n[1-2 sentences. State the conclusion directly.]\n\n"
        "## Evidence Chain\n[Each signal: what it shows -> mechanism -> consequence. Cite (source, date).]\n\n"
        "## Confidence\n[XX% -- how many independent signals? Convergent or contradictory?]\n\n"
        "## Counter-signals\n[What in the corpus argues against? If none -- state why.]\n\n"
        "## Watch For\n[2-3 specific events in next 30 days that confirm or deny this.]\n\n"
        "RULE: use ONLY corpus facts. Cite every claim. "
        "If insufficient data, say so explicitly -- do not fill gaps with assumptions."
    )

    _system = (
        f"{_lang_rule}"
        "You are a professional intelligence analyst. "
        "Your response MUST begin with a '##' heading -- nothing before it. "
        "No preamble. No meta-commentary. Answer the specific question using only corpus evidence."
    )
    _prompt = "\n".join(corpus) + "\n\n" + _instructions
    _messages = [
        {"role": "system", "content": _system},
        {"role": "user",   "content": _prompt},
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

    m = re.search(r"^##", result, re.MULTILINE)
    if m:
        result = result[m.start():]

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
