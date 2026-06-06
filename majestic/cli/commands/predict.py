"""/predict [days] — single-section, real-data, cross-sector forecasts (Phase J).

One ranked list: prediction + reason, grounded in the research/prices corpus,
with cross-sector intersection probabilities. 4 anchor niches are always
tracked (fluctuation shown run-to-run); the rest emerge from the news.
"""

import json
import time
from datetime import date

from majestic.cli.commands.context import CommandContext
from majestic.cli.commands.registry import command
from majestic.intelligence import generate_predictions, load_recent_briefing
from majestic.intelligence.predict import (
    _load_prev_anchors,
    _apply_trend,
    _save_anchors,
    render_markdown,
)


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

    # ── Gather corpus ───────────────────────────────────────────────────────
    articles: list[dict] = []
    prices_block = ""
    try:
        db = ctx.backend.research()
        articles = db.get_articles(days=days)
        try:
            prices, prices_ts = db.get_latest_prices()
            if prices:
                from majestic.tools.research.prices import format_prices_for_corpus as _fmt
                prices_block = _fmt(prices, prices_ts) or ""
        except Exception:
            pass
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
    anchors = ctx.settings.anchor_niches

    _display.tree_reset()
    if briefing:
        _display.tree_step("Briefing", "macro context loaded")
    if prices_block:
        _display.tree_step("Prices", "live market snapshot")
    _display.tree_step("Research DB", f"{len(articles)} articles")
    _display.tree_step("Pains DB", f"{len(pains)} pain points")
    _display.tree_step("Anchors", " · ".join(anchors))

    _lang = getattr(ctx.settings, "agent_language", "") or "en"

    # ── Generate ────────────────────────────────────────────────────────────
    t0 = time.monotonic()
    result_md = ""
    items: list[dict] = []
    raw = ""
    try:
        with _display.TreePending("forecasting..."):
            out = await generate_predictions(
                llm=ctx.runtime.llm,
                articles=articles,
                pains=pains,
                briefing=briefing or "",
                prices_block=prices_block,
                anchors=anchors,
                days=days,
                lang=_lang,
            )
        _display.tree_close()
        items = out["items"]
        raw = out.get("raw", "")
        ctx.runtime._tokens_used = out["tokens"]
        ctx.runtime._cost_used = out["cost"]
    except Exception as exc:
        _display.tree_close("error")
        result_md = f"Error: {exc}"
    elapsed = time.monotonic() - t0

    # ── Fluctuation (anchors) + persist ─────────────────────────────────────
    ws = ctx.settings.workspace_dir
    if items:
        prev = _load_prev_anchors(ws)
        _apply_trend(items, prev)
        result_md = render_markdown(items, days)
        _save_anchors(ws, items)

    try:
        pred_dir = ws / "predictions"
        pred_dir.mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()
        (pred_dir / f"{today}.md").write_text(result_md, encoding="utf-8")
        if items:
            (pred_dir / f"{today}.json").write_text(
                json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        elif raw:
            (pred_dir / f"{today}.raw.txt").write_text(raw, encoding="utf-8")
        _display.tree_reset()
        _display.tree_step("saved", f"{today}.md")
        _display.tree_close()
    except Exception:
        pass

    if ctx.channel is not None:
        await ctx.channel.send(f"\n{result_md}\n")
    else:
        ctx.out(result_md)

    from majestic import display as _d
    _d.inline_stats(
        tokens=getattr(ctx.runtime, "_tokens_used", 0),
        cost=getattr(ctx.runtime, "_cost_used", 0.0),
        elapsed=elapsed,
    )
    return True
