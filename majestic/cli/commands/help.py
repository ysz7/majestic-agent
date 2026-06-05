"""/help — list available slash commands."""

from majestic.cli.commands.context import CommandContext
from majestic.cli.commands.registry import command

_COMMANDS = {
    "/research":    "Fetch curated news → summary + live market snapshot",
    "/pains":       "Extract pain points (intensity, WTP, trending domains)",
    "/ideas":       "Generate startup ideas from the accumulated pains corpus",
    "/products":    "TOP-10 sellable solo digital products + monetization audit",
    "/predict":     "Forecasts grounded in live market data",
    "/briefing":    "Daily briefing from the news corpus + market snapshot",
    "/news":        "Show stored news from the last N days (no re-fetch)",
    "/goodmorning": "Full pipeline: research → pains → briefing → ideas → predict",
    "/ask":         "Answer a question against the research + pains corpus",
    "/skills":      "List loaded skills with descriptions",
    "/tools":       "List all registered tools",
    "/agents":      "Show running background agents",
    "/memory":      "Memory stats — episodic tasks, lessons, semantic index",
    "/budget":      "Current token and cost usage for this session",
    "/new":         "Clear session and reset working memory",
    "/help":        "Show this help",
}


@command("/help")
async def handle(ctx: CommandContext):
    ctx.out("[bold]Available commands:[/bold]")
    for c, desc in _COMMANDS.items():
        ctx.out(f"  [cyan]{c:<13}[/cyan]  [dim]{desc}[/dim]")
    return True
