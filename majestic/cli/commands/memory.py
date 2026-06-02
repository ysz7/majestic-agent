"""/memory — quick memory stats for the active profile."""

from majestic.cli.commands.context import CommandContext
from majestic.cli.commands.registry import command


@command("/memory")
async def handle(ctx: CommandContext):
    try:
        from majestic.display import _gather_startup
        d = _gather_startup(ctx.profile_name)
        mem = d.get("mem_count", 0)
        les = d.get("lessons_count", 0)
        ctx.out(
            f"[bold]Memory:[/bold]\n"
            f"  [dim]episodic · [/dim]{mem} tasks\n"
            f"  [dim]lessons  · [/dim]{les}\n"
            f"  [dim]semantic · [/dim]sqlite-vec"
        )
    except Exception as e:
        ctx.out(f"[red]Error: {e}[/red]")
    return True
