"""/briefing [days] — deep intelligence briefing from the stored news corpus.

Thin handler (Phase K.6): fetch data + display + persist here; the corpus +
prompt + LLM generation lives in ``intelligence.generate_briefing``.
"""

import time
from datetime import date

from majestic.cli.commands.context import CommandContext
from majestic.cli.commands.registry import command
from majestic.intelligence import generate_briefing


@command("/briefing")
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

    prices: list[dict] = []
    prices_ts = ""
    prices_block = ""
    try:
        db2 = ctx.backend.research()
        prices, prices_ts = db2.get_latest_prices()
        db2.close()
        if prices:
            from majestic.tools.research.prices import format_prices_for_corpus as _fmt
            prices_block = _fmt(prices, prices_ts) or ""
    except Exception:
        pass

    _display.tree_reset()
    _display.tree_step("Research DB", f"{stats['total']} total · last {days}d: {len(articles)} articles")
    if prices:
        _display.tree_step("Prices", f"{len(prices)} assets · {prices_ts[:16]}")

    _lang = getattr(ctx.settings, "agent_language", "") or "en"

    t0 = time.monotonic()
    result = ""
    try:
        with _display.TreePending("analyzing..."):
            out = await generate_briefing(
                llm=ctx.runtime.llm,
                articles=articles,
                prices_block=prices_block,
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
