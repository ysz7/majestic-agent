"""/agents — show running background agents from the registry."""

from majestic.cli.commands.context import CommandContext
from majestic.cli.commands.registry import command


@command("/agents")
async def handle(ctx: CommandContext):
    try:
        from majestic.cli.registry_db import load_registry
        data = load_registry()
        if not data:
            ctx.out("[dim]No background agents running. Start one with: majestic run <profile>[/dim]")
        else:
            ctx.out("[bold]Running agents:[/bold]")
            for name, info in data.items():
                port = info.get("port", "?")
                status = info.get("status", "?")
                dot = "[green]●[/green]" if status == "running" else "[yellow]●[/yellow]"
                ctx.out(f"  {dot} [bold]{name}[/bold]  [dim]:{port}  {status}[/dim]")
    except Exception as e:
        ctx.out(f"[red]Error: {e}[/red]")
    return True
