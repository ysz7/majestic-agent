"""/budget — token and cost usage for the current session."""

from majestic.cli.commands.context import CommandContext
from majestic.cli.commands.registry import command


@command("/budget")
async def handle(ctx: CommandContext):
    tokens = getattr(ctx.runtime, "_tokens_used", 0)
    cost = getattr(ctx.runtime, "_cost_used", 0.0)
    ctx.out(
        f"[bold]Budget:[/bold]\n"
        f"  [dim]tokens · [/dim]{tokens:,}\n"
        f"  [dim]cost   · [/dim]${cost:.4f}"
    )
    return True
