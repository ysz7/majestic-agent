"""/products [days] — generate TOP-N sellable solo digital products with
monetization audits, synthesized from the accumulated intelligence corpus."""

import json
import re
import time
from datetime import date

from majestic.cli.commands.context import CommandContext
from majestic.cli.commands.registry import command
from majestic.intelligence import (
    generate_solo_products,
    load_recent_briefing,
)

_DEFAULT_N = 10


@command("/products")
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
        ctx.out("[red]No settings -- /products requires a profile.[/red]")
        return True

    # ── Gather corpus data ──────────────────────────────────────────────────
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

    # Avoid repeating products already generated recently.
    past_names: list[str] = []
    try:
        prod_dir = ctx.settings.workspace_dir / "products"
        if prod_dir.exists():
            recent = sorted(prod_dir.glob("*.json"), reverse=True)[:3]
            for f in recent:
                data = json.loads(f.read_text(encoding="utf-8"))
                past_names.extend(it.get("name", "") for it in data if isinstance(it, dict))
    except Exception:
        pass

    _display.tree_reset()
    if briefing:
        _display.tree_step("Briefing", "macro context loaded")
    _display.tree_step("Research DB", f"{len(articles)} articles")
    _display.tree_step("Pains DB", f"{len(pains)} pain points")
    if past_names:
        _display.tree_step("History", f"{len(past_names)} past products (avoid repeats)")

    _lang = getattr(ctx.settings, "agent_language", "") or "en"

    # ── Generate ────────────────────────────────────────────────────────────
    t0 = time.monotonic()
    result_md = ""
    items: list[dict] = []
    raw = ""
    try:
        with _display.TreePending("forging products..."):
            out = await generate_solo_products(
                llm=ctx.runtime.llm,
                articles=articles,
                pains=pains,
                briefing=briefing or "",
                past_names=past_names,
                n=_DEFAULT_N,
                days=days,
                lang=_lang,
            )
        _display.tree_close()
        items = out["items"]
        result_md = out["markdown"]
        raw = out.get("raw", "")
        ctx.runtime._tokens_used = out["tokens"]
        ctx.runtime._cost_used = out["cost"]
    except Exception as exc:
        _display.tree_close("error")
        result_md = f"Error: {exc}"
    elapsed = time.monotonic() - t0

    # ── Persist ─────────────────────────────────────────────────────────────
    try:
        prod_dir = ctx.settings.workspace_dir / "products"
        prod_dir.mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()
        (prod_dir / f"{today}.md").write_text(result_md, encoding="utf-8")
        if items:
            (prod_dir / f"{today}.json").write_text(
                json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        elif raw:
            (prod_dir / f"{today}.raw.txt").write_text(raw, encoding="utf-8")
        _display.tree_reset()
        _display.tree_step("saved", f"{today}.md")

        # Save the top 3 to lessons so future runs avoid repeats.
        if items:
            try:
                ls = ctx.backend.lessons()
                for it in items[:3]:
                    block = f"{it.get('name','')} — {it.get('one_liner','')} " \
                            f"(score {it.get('sellability_score','')})"
                    ls.save(task_type="products", lesson=block[:600])
                ls._conn.close()
                _display.tree_step("memory", "top 3 saved to lessons")
            except Exception:
                pass
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
