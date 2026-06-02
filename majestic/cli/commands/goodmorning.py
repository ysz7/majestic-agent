"""/goodmorning [days] — run the full intelligence pipeline in sequence."""

from majestic.cli.commands.context import CommandContext
from majestic.cli.commands.registry import command


@command("/goodmorning")
async def handle(ctx: CommandContext):
    from majestic.cli.commands import dispatch

    words = ctx.text.strip().split()
    days = 30
    if len(words) > 1:
        try:
            days = int(words[1])
        except ValueError:
            pass

    ctx.out(f"\n[bold]Good Morning[/bold] [dim]— full intelligence pipeline · last {days}d[/dim]\n")

    async def _step(n: int, label: str, cmd: str) -> None:
        ctx.out(f"[dim]━━ {n}/5  {label}[/dim]\n")
        sub = CommandContext(
            text=cmd, profile_name=ctx.profile_name,
            working_memory=ctx.working_memory, runtime=ctx.runtime,
            settings=ctx.settings, semantic=ctx.semantic,
            channel=ctx.channel, gateway=ctx.gateway,
            backend=ctx.backend, console=ctx.console,
        )
        # Fall through to _handle_slash_plain for commands not yet in registry
        result = await dispatch(sub)
        if result is None:
            from majestic.cli.foreground import _handle_slash_plain
            await _handle_slash_plain(
                cmd, ctx.profile_name, ctx.working_memory, ctx.runtime,
                ctx.settings, ctx.semantic, ctx.channel, ctx.gateway,
            )

    await _step(1, "/research — fetching news...",          "/research")
    await _step(2, "/pains — scanning community signals...", "/pains")
    await _step(3, f"/briefing {days} — analyzing...",       f"/briefing {days}")
    await _step(4, f"/predict {days} — generating...",       f"/predict {days}")
    await _step(5, f"/ideas {days} — generating ideas...",   f"/ideas {days}")

    ctx.out("\n[green]OK[/green] [dim]Pipeline complete.[/dim]")
    return True
