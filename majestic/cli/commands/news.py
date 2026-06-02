"""/news [days] — show stored articles from the DB without re-fetching."""

from collections import defaultdict

from majestic.cli.commands.context import CommandContext
from majestic.cli.commands.registry import command


@command("/news")
async def handle(ctx: CommandContext):
    words = ctx.text.strip().split()
    days = 7
    if len(words) > 1:
        try:
            days = int(words[1])
        except ValueError:
            pass

    if ctx.settings is None:
        ctx.out("[dim]News requires a profile with a research DB. Run /research first.[/dim]")
        return True

    try:
        db = ctx.backend.research()
        articles = db.get_articles(days=days)
        db.close()
    except Exception as e:
        ctx.out(f"[red]DB error: {e}[/red]")
        return True

    if not articles:
        ctx.out(f"[dim]No articles for the last {days} days. Run /research first.[/dim]")
        return True

    by_cat: dict[str, list] = defaultdict(list)
    for a in articles:
        by_cat[a.get("category", "general")].append(a)

    ctx.out(f"\n[bold]NEWS[/bold]  [dim]last {days} days · {len(articles)} articles[/dim]\n")
    for cat in sorted(by_cat):
        items = by_cat[cat]
        dashes = "-" * max(0, 48 - len(cat))
        ctx.out(f"  [bold cyan]{cat.upper()}[/bold cyan]  [dim]{dashes}[/dim]")
        for a in items[:25]:
            date   = a.get("date", "")
            title  = a.get("title", "")
            title  = (title[:68] + "...") if len(title) > 68 else title
            source = a.get("source", "")
            url    = a.get("url", "").replace("https://", "").replace("http://", "")
            url    = (url[:66] + "...") if len(url) > 66 else url
            ctx.out(f"  [dim]{date}[/dim]  {title}  [dim]· {source}[/dim]")
            if url:
                ctx.out(f"  [dim]          {url}[/dim]")
        if len(items) > 25:
            ctx.out(f"  [dim]          ... and {len(items) - 25} more[/dim]")
        ctx.out("")
    return True
