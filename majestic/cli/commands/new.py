"""/new — clear the session and reset working memory."""

from majestic.cli.commands.context import CommandContext
from majestic.cli.commands.registry import command


@command("/new")
async def handle(ctx: CommandContext):
    ctx.working_memory.clear()
    ctx.out("[dim]Session cleared.[/dim]")
    return True
