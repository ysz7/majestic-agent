"""/tools — list tools registered on the runtime."""

from majestic.cli.commands.context import CommandContext
from majestic.cli.commands.registry import command


@command("/tools")
async def handle(ctx: CommandContext):
    tools = list(getattr(ctx.runtime, "tools", {}).keys())
    if not tools:
        ctx.out("[dim]No tools registered.[/dim]")
    else:
        ctx.out("[bold]Available tools:[/bold]")
        for t in tools:
            ctx.out(f"  [cyan]{t}[/cyan]")
    return True
