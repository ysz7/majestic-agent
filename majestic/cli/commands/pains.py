"""/pains [days] — extract and store pain signals, or show stored ones."""

from collections import defaultdict

from majestic.cli.commands.context import CommandContext
from majestic.cli.commands.registry import command


@command("/pains")
async def handle(ctx: CommandContext):
    from majestic import display as _display

    words = ctx.text.strip().split()
    days: int | None = None
    if len(words) > 1:
        try:
            days = int(words[1])
        except ValueError:
            pass

    # ── DB-read mode ──────────────────────────────────────────────────────────
    if days is not None:
        if ctx.settings is None:
            ctx.out("[dim]No profile loaded — cannot read from pains DB.[/dim]")
            return True
        try:
            db = ctx.backend.pains()
            stored = db.get_pains(days=days)
            trends: list[dict] = []
            try:
                trends = db.get_trending_domains()
            except Exception:
                pass
            db.close()
        except Exception as e:
            ctx.out(f"[red]DB error: {e}[/red]")
            return True

        if not stored:
            ctx.out(f"[dim]No pain points in DB for the last {days} days. Run /pains (no args) to scan sources.[/dim]")
            return True

        by_dom: dict = defaultdict(list)
        for p in stored:
            by_dom[p.get("domain", "other")].append(p)

        lines = [f"\n## Pain Radar -- {len(stored)} stored · last {days}d\n"]
        trend_parts: list[str] = []
        for t in trends[:6]:
            if t["delta_pct"] >= 20:
                trend_parts.append(f"^ {t['domain']}: +{t['delta_pct']}%")
            elif t["delta_pct"] <= -20:
                trend_parts.append(f"v {t['domain']}: {t['delta_pct']}%")
        if trend_parts:
            lines.append("  ".join(trend_parts[:5]) + "\n")

        for dom, items in sorted(by_dom.items(), key=lambda x: -len(x[1])):
            lines.append(f"### {dom.upper()} ({len(items)})")
            for p in items[:6]:
                src = f"[{p.get('source', '')}] " if p.get("source") else ""
                tag = (" [HIGH]" if p.get("intensity") == "HIGH" else "") + (" WTP" if p.get("willingness_to_pay") else "")
                lines.append(f"- {src}{p.get('pain_text', '')}{tag}")
            lines.append("")

        result = "\n".join(lines)
        if ctx.channel is not None:
            await ctx.channel.send(result)
        else:
            ctx.out(result)
        return True

    # ── Fresh-fetch mode ──────────────────────────────────────────────────────
    ctx.out("[dim]Scanning pain-signal sources...[/dim]")
    _display.tree_reset()

    def _on_source(name: str, count: int, success: bool) -> None:
        if success:
            _display.tree_step(name, f"{count} post{'s' if count != 1 else ''}")
        else:
            _display.tree_step(name, "no response", status="warn")

    try:
        from majestic.tools.pains import fetch_all as _fetch_all, extract_pains as _extract
        posts, ok_sources, failed = await _fetch_all(on_source=_on_source)
    except Exception as e:
        ctx.out(f"[red]Fetch error: {e}[/red]")
        return True

    if not posts:
        ctx.out("[dim]No posts fetched. Check your internet connection.[/dim]")
        return True

    new_posts: list[dict] = posts
    pdb = None
    if ctx.settings is not None:
        try:
            pdb = ctx.backend.pains()
            new_posts, skipped = pdb.insert_posts(posts)
            _display.tree_step("saved", f"{len(new_posts)} new · {skipped} cached")
        except Exception as e:
            ctx.out(f"[yellow]DB warning: {e}[/yellow]")

    if not new_posts:
        ctx.out("[dim]No new posts since last /pains.[/dim]")
        if pdb:
            pdb.close()
        return True

    _lang = getattr(ctx.settings, "agent_language", "en") or "en"
    pains: list[dict] = []
    try:
        with _display.TreePending(f"extracting pains from {min(len(new_posts), 60)} posts..."):
            pains = await _extract(new_posts, ctx.runtime.llm, lang=_lang)
    except Exception as e:
        ctx.out(f"[yellow]Extraction warning: {e}[/yellow]")

    if pdb and pains:
        try:
            n = pdb.insert_pains(pains)
            stats = pdb.stats()
            _display.tree_step("pains", f"{n} extracted · {stats['total_pains']} total in DB")
        except Exception as e:
            ctx.out(f"[yellow]Pain save warning: {e}[/yellow]")

    trend_line = ""
    if pdb:
        try:
            td = pdb.get_trending_domains()
            tp: list[str] = []
            for t in td[:6]:
                if t["delta_pct"] >= 20:
                    tp.append(f"^ {t['domain']}: +{t['delta_pct']}%")
                elif t["delta_pct"] <= -20:
                    tp.append(f"v {t['domain']}: {t['delta_pct']}%")
            if tp:
                trend_line = "  ".join(tp[:5])
        except Exception:
            pass
        pdb.close()

    _display.tree_close()

    if not pains:
        ctx.out("[dim]No pain points extracted from new posts.[/dim]")
        return True

    by_domain: dict = defaultdict(list)
    for p in pains:
        by_domain[p.get("domain", "other")].append(p)

    summary = [f"\n## Pain Radar -- {len(pains)} pain points · {len(ok_sources)} sources\n"]
    if trend_line:
        summary.append(trend_line + "\n")
    for domain, items in sorted(by_domain.items(), key=lambda x: -len(x[1])):
        summary.append(f"### {domain.upper()} ({len(items)})")
        for p in items[:6]:
            src = f"[{p.get('source', '')}] " if p.get("source") else ""
            tag = (" [HIGH]" if p.get("intensity") == "HIGH" else "") + (" WTP" if p.get("willingness_to_pay") else "")
            summary.append(f"- {src}{p.get('pain_text', '')}{tag}")
        summary.append("")

    result = "\n".join(summary)
    if ctx.channel is not None:
        await ctx.channel.send(result)
    else:
        ctx.out(result)
    return True
