"""/ideas [days] — generate startup ideas from the accumulated corpus.

Thin handler (Phase K.6): fetch data + display + persist here; the corpus +
prompt + LLM generation lives in ``intelligence.generate_ideas``.
"""

import re
import time
from collections import Counter
from datetime import date

from majestic.cli.commands.context import CommandContext
from majestic.cli.commands.registry import command
from majestic.intelligence import generate_ideas, load_recent_briefing


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

    high_demand = [p for p in pains_all if p.get("intensity") == "HIGH" or p.get("willingness_to_pay")]
    launches = [a for a in articles if a.get("category") == "launches"]
    news = [a for a in articles if a.get("category") != "launches"]

    # Recall recent ideas so the model finds NEW angles (backend-specific).
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

    _lang = getattr(ctx.settings, "agent_language", "") or "en"

    t0 = time.monotonic()
    result = ""
    try:
        with _display.TreePending("generating ideas..."):
            out = await generate_ideas(
                llm=ctx.runtime.llm,
                pains=pains_all,
                articles=articles,
                briefing=briefing or "",
                past_ideas=past_ideas,
                days=days,
                lang=_lang,
            )
        _display.tree_close()
        result = out["markdown"]
        ctx.runtime._tokens_used = out["tokens"]
        ctx.runtime._cost_used = out["cost"]
    except Exception as exc:
        _display.tree_close("error")
        result = f"Error: {exc}"
    elapsed = time.monotonic() - t0

    try:
        ideas_dir = ctx.settings.workspace_dir / "ideas"
        ideas_dir.mkdir(parents=True, exist_ok=True)
        fn = ideas_dir / f"{date.today().isoformat()}.md"
        fn.write_text(result, encoding="utf-8")
        _display.tree_reset()
        _display.tree_step("saved", fn.name)

        # Save the top 3 ideas to lessons so future runs avoid repeats.
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
