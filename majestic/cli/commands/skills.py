"""/skills — list loaded skills for the active profile."""

from majestic.cli.commands.context import CommandContext
from majestic.cli.commands.registry import command


@command("/skills")
async def handle(ctx: CommandContext):
    try:
        from majestic.display import _gather_startup
        d = _gather_startup(ctx.profile_name)
        skills = d.get("skills", [])
        if not skills:
            ctx.out("[dim]No skills loaded yet. Add YAML files to profiles/<name>/skills/[/dim]")
        else:
            ctx.out("[bold]Loaded skills:[/bold]")
            for sk in skills:
                name = sk.get("name", "?")
                raw = sk.get("description", "")
                desc = (raw[:57] + "…") if len(raw) > 60 else raw
                ctx.out(f"  [cyan]/{name:<18}[/cyan] [dim]{desc}[/dim]")
    except Exception as e:
        ctx.out(f"[red]Error: {e}[/red]")
    return True
