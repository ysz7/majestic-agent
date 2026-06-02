"""/research — fetch curated news, store, summarize + market snapshot."""

from majestic.cli.commands.context import CommandContext
from majestic.cli.commands.registry import command
from majestic.core.intelligence import llm_with_retry


@command("/research")
async def handle(ctx: CommandContext):
    from majestic import display as _display
    ctx.out("[dim]Connecting to curated sources...[/dim]")
    _display.tree_reset()

    def _on_source(name: str, count: int, success: bool) -> None:
        if success:
            _display.tree_step(name, f"{count} article{'s' if count != 1 else ''}")
        else:
            _display.tree_step(name, "no response", status="warn")

    try:
        from majestic.tools.research import fetch_all
        articles, ok_sources, failed = await fetch_all(on_source=_on_source)
    except Exception as e:
        ctx.out(f"[red]Fetch error: {e}[/red]")
        return True

    new_articles: list[dict] = articles
    if ctx.settings is not None:
        try:
            db = ctx.backend.research()
            new_articles, skipped = db.insert_articles(articles)
            stats = db.stats()
            db.close()
            _display.tree_step(
                "saved",
                f"{len(new_articles)} new · {skipped} cached · {stats['total']} total",
            )
        except Exception as e:
            _display.tree_step("saved", f"DB error: {e}", status="warn")

        if ctx.semantic is not None and new_articles:
            try:
                for a in new_articles:
                    chunk = f"{a['title']}. {a.get('summary', '')}"
                    ctx.semantic.index(
                        source=a.get("url") or a.get("source", "research"),
                        content=chunk,
                    )
            except Exception:
                pass

    _prices: list[dict] = []
    _prices_ts: str = ""
    if ctx.settings is not None:
        try:
            from majestic.tools.research.prices import fetch_prices as _fetch_prices
            from datetime import datetime as _dt, timezone as _tz
            with _display.TreePending("prices..."):
                _prices = await _fetch_prices()
            if _prices:
                _prices_ts = _dt.now(_tz.utc).isoformat(timespec="seconds")
                db2 = ctx.backend.research()
                db2.insert_prices(_prices)
                db2.close()
                _display.tree_step("prices", f"{len(_prices)} assets updated")
            else:
                _display.tree_step("prices", "no data", status="warn")
        except Exception as pe:
            _display.tree_step("prices", f"skipped: {pe}", status="warn")

    if not articles:
        _display.tree_close()
        ctx.out("[dim]No articles fetched. Check your internet connection.[/dim]")
        return True

    if not new_articles:
        _display.tree_close()
        ctx.out("[dim]No new articles since last /research. Use /briefing to analyze stored news.[/dim]")
        return True

    _display.tree_close()

    _lang = getattr(ctx.settings, "agent_language", "") or "en"
    _lang_note = (
        f" Respond in {_lang}. Article titles may stay in original language."
        if _lang and _lang.lower() not in ("en", "english") else ""
    )
    _art_lines: list[str] = []
    for a in new_articles[:40]:
        _art_lines.append(f"[{a.get('category','?').upper()}] {a.get('source','?')} · {a.get('date','')}:")
        _art_lines.append(f"  {a.get('title','')}")
        if a.get("summary"):
            _art_lines.append(f"  {a.get('summary','')[:180]}")
        _art_lines.append("")

    _prompt = (
        f"Here are {len(new_articles)} new articles from {len(ok_sources)} sources "
        f"(previously seen articles excluded):\n\n"
        + "\n".join(_art_lines)
        + f"\nWrite a concise briefing.{_lang_note} "
        "Structure: 1) Top stories, 2) Tech & AI, 3) Business & Finance, 4) Science & World. "
        "Mention real names and numbers. Under 400 words."
    )
    _sys = (
        "You are a news analyst. Begin directly with the briefing — "
        "no preamble, no meta-commentary."
    )
    _messages = [
        {"role": "system", "content": _sys},
        {"role": "user",   "content": _prompt},
    ]
    import time as _time
    _t0 = _time.monotonic()
    try:
        with _display.TreePending("summarizing..."):
            _resp = await llm_with_retry(ctx.runtime.llm, _messages, step_type="simple")
        _display.tree_close()
        _summary = _resp.get("content", "").strip()
        ctx.runtime._tokens_used = _resp.get("input_tokens", 0) + _resp.get("output_tokens", 0)
        ctx.runtime._cost_used = _resp.get("cost") or 0.0
    except Exception as exc:
        _display.tree_close("error")
        _summary = f"(summary unavailable: {exc})"
    _elapsed = _time.monotonic() - _t0

    if ctx.channel is not None:
        await ctx.channel.send(f"\n{_summary}\n")
    else:
        ctx.out(_summary)

    if _prices:
        from majestic.tools.research.prices import (
            render_prices_table as _rpt,
            format_prices_markdown as _fmt_md,
            format_prices_for_display as _fmt_prices,
        )
        _table = _rpt(_prices, _prices_ts)
        if ctx.channel is not None and _table is not None and hasattr(ctx.channel, "send_renderable"):
            await ctx.channel.send_renderable(_table)
        elif ctx.channel is not None:
            _md = _fmt_md(_prices, _prices_ts)
            if _md:
                await ctx.channel.send(f"\n{_md}\n")
        elif _table is not None and ctx.console:
            ctx.console.print()
            ctx.console.print(_table)
        else:
            ctx.out(f"\n{_fmt_prices(_prices)}\n")

    from majestic import display as _d
    _d.inline_stats(
        tokens=getattr(ctx.runtime, "_tokens_used", 0),
        cost=getattr(ctx.runtime, "_cost_used", 0.0),
        elapsed=_elapsed,
    )
    return True
