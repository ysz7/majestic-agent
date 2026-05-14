from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static


class Sidebar(Widget):
    def __init__(self, profile_name: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._profile_name = profile_name
        self._data: dict = {}

    def compose(self) -> ComposeResult:
        yield Static("", id="sidebar-content")

    def on_mount(self) -> None:
        self._refresh_data()
        self.set_interval(5.0, self._refresh_data)

    def _refresh_data(self) -> None:
        try:
            from majestic.display import _gather_startup
            self._data = _gather_startup(self._profile_name)
        except Exception:
            pass
        self.query_one("#sidebar-content", Static).update(self._build_content())

    def _build_content(self) -> str:
        d = self._data
        W = 22  # content width

        def sec(title: str) -> str:
            dashes = "─" * max(0, W - len(title) - 1)
            return f"[#d95767]{title}[/] [dim]{dashes}[/dim]"

        def row(label: str, value: str) -> str:
            # Only truncate plain strings — never cut inside a markup tag
            if "[" not in value:
                value = value[: W - len(label) - 3]
            return f"  [dim]{label} ·[/dim] {value}"

        lines: list[str] = []

        # ── AGENT ─────────────────────────────────────────────────────────
        lines.append(sec("AGENT"))
        lines.append(row("name  ", d.get("agent_name", "—")))
        role = (d.get("role") or "—")[:14]
        lines.append(row("role  ", role))
        api_dot = "[green]●[/green] ok" if d.get("api_ok") else "[red]●[/red] missing"
        lines.append(row("api   ", api_dot))
        brave = "[green]●[/green] Brave" if d.get("has_brave") else "[yellow]●[/yellow] DDG"
        lines.append(row("search", brave))
        lines.append("")

        # ── MODEL ─────────────────────────────────────────────────────────
        lines.append(sec("MODEL"))
        model = d.get("model", "—") or "—"
        lines.append(row("model", model.split("/")[-1][:18]))
        lines.append("")

        # ── MEMORY ────────────────────────────────────────────────────────
        lines.append(sec("MEMORY"))
        mem = d.get("mem_count", 0)
        les = d.get("lessons_count", 0)
        lines.append(row("episodic", f"{mem} tasks"))
        lines.append(row("lessons ", f"{les}"))
        lines.append(row("semantic", "sqlite-vec"))
        lines.append("")

        # ── SKILLS ────────────────────────────────────────────────────────
        lines.append(sec("SKILLS"))
        skills = d.get("skills", [])
        skill_count = d.get("skill_count", 0)
        if skills:
            for sk in skills[:4]:
                name = ("/" + sk.get("name", "?"))[:W]
                lines.append(f"  [dim]{name}[/dim]")
            if skill_count > 4:
                lines.append(f"  [dim]+ {skill_count - 4} more[/dim]")
        else:
            lines.append("  [dim]none yet[/dim]")
        lines.append("")

        # ── RUNNING AGENTS ────────────────────────────────────────────────
        lines.append(sec("RUNNING AGENTS"))
        agents = d.get("running_agents", [])
        if agents:
            for ag in agents[:4]:
                name = ag["name"][:10]
                port = ag.get("port", "?")
                dot = "[green]●[/green]" if ag.get("status") == "running" else "[yellow]●[/yellow]"
                lines.append(f"  {dot} [dim]{name}[/dim] :{port}")
        else:
            lines.append("  [dim]none running[/dim]")

        return "\n".join(lines)
