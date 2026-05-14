from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .app import MajesticApp

SLASH_COMMANDS = {
    "/help":   "Show available commands",
    "/skills": "List loaded skills with descriptions",
    "/agents": "Show running agents (like majestic ps)",
    "/memory": "Show memory stats",
    "/budget": "Show current token/cost usage",
    "/new":    "Start fresh session (clear chat, reset working memory)",
    "/quit":   "Exit gracefully",
}


def handle_slash_command(text: str, app: "MajesticApp") -> str | None:
    """Handle a slash command. Returns a string to display, or None to send to agent."""
    cmd = text.strip().lower().split()[0]

    if cmd == "/help":
        lines = ["[bold]Available commands:[/bold]"]
        for c, desc in SLASH_COMMANDS.items():
            lines.append(f"  [cyan]{c:<10}[/cyan] [dim]{desc}[/dim]")
        return "\n".join(lines)

    if cmd == "/quit":
        app._input_queue.put_nowait(None)
        app.exit()
        return "Goodbye!"

    if cmd == "/skills":
        try:
            from majestic.display import _gather_startup
            d = _gather_startup(app.profile_name)
            skills = d.get("skills", [])
            if not skills:
                return "[dim]No skills loaded yet. Add YAML files to profiles/<name>/skills/[/dim]"
            lines = ["[bold]Loaded skills:[/bold]"]
            for sk in skills:
                name = sk.get("name", "?")
                desc = sk.get("description", "")[:60]
                lines.append(f"  [cyan]/{name:<18}[/cyan] [dim]{desc}[/dim]")
            return "\n".join(lines)
        except Exception as e:
            return f"[red]Error loading skills: {e}[/red]"

    if cmd == "/agents":
        try:
            import json
            from pathlib import Path
            reg = Path(__file__).resolve().parent.parent.parent.parent / "data" / "registry.json"
            if not reg.exists():
                return "[dim]No background agents running. Start one with: majestic run <profile>[/dim]"
            data = json.loads(reg.read_text())
            if not data:
                return "[dim]No background agents running. Start one with: majestic run <profile>[/dim]"
            lines = ["[bold]Running agents:[/bold]"]
            for name, info in data.items():
                port = info.get("port", "?")
                status = info.get("status", "?")
                dot = "[green]●[/green]" if status == "running" else "[yellow]●[/yellow]"
                lines.append(f"  {dot} [bold]{name}[/bold]  [dim]:{port}  {status}[/dim]")
            return "\n".join(lines)
        except Exception as e:
            return f"[red]Error: {e}[/red]"

    if cmd == "/memory":
        try:
            from majestic.display import _gather_startup
            d = _gather_startup(app.profile_name)
            mem = d.get("mem_count", 0)
            les = d.get("lessons_count", 0)
            return (
                f"[bold]Memory stats:[/bold]\n"
                f"  [dim]episodic · [/dim]{mem} tasks\n"
                f"  [dim]lessons  · [/dim]{les}\n"
                f"  [dim]semantic · [/dim]sqlite-vec"
            )
        except Exception as e:
            return f"[red]Error: {e}[/red]"

    if cmd == "/budget":
        status = app.query_one("StatusBar")
        tok = getattr(status, "_tokens", 0)
        tok_lim = getattr(status, "_tokens_limit", 0)
        cost = getattr(status, "_cost", 0.0)
        cost_lim = getattr(status, "_cost_limit", 0.0)
        tok_lim_str = str(tok_lim) if tok_lim else "unlimited"
        cost_lim_str = f"${cost_lim:.2f}" if cost_lim else "unlimited"
        return (
            f"[bold]Budget usage:[/bold]\n"
            f"  [dim]tokens · [/dim]{tok:,} / {tok_lim_str}\n"
            f"  [dim]cost   · [/dim]${cost:.4f} / {cost_lim_str}"
        )

    if cmd == "/new":
        try:
            app.query_one("ChatPane").on_mount()
        except Exception:
            pass
        return "[dim]Session cleared.[/dim]"

    # Unknown slash command — let the agent handle it
    return None
