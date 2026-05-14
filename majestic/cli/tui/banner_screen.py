from __future__ import annotations

from datetime import date
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Static
from textual.containers import Vertical


_LOGO = [
    "███╗   ███╗ █████╗      ██╗███████╗███████╗████████╗██╗ ██████╗ ",
    "████╗ ████║██╔══██╗     ██║██╔════╝██╔════╝╚══██╔══╝██║██╔════╝ ",
    "██╔████╔██║███████║     ██║█████╗  ███████╗   ██║   ██║██║      ",
    "██║╚██╔╝██║██╔══██║██   ██║██╔══╝  ╚════██║   ██║   ██║██║      ",
    "██║ ╚═╝ ██║██║  ██║╚█████╔╝███████╗███████║   ██║   ██║╚██████╗ ",
    "╚═╝     ╚═╝╚═╝  ╚═╝ ╚════╝ ╚══════╝╚══════╝   ╚═╝   ╚═╝ ╚═════╝",
]


class BannerScreen(ModalScreen):
    CSS = """
    BannerScreen {
        align: center middle;
        background: $background 80%;
    }
    #banner-box {
        width: 72;
        padding: 1 2;
        border: solid #d95767;
        background: #1a1a1a;
    }
    #banner-logo {
        color: #d95767;
        text-style: bold;
    }
    #banner-info {
        color: #888888;
        margin-top: 1;
    }
    #banner-hint {
        color: #555555;
        margin-top: 1;
        text-align: center;
    }
    """

    def __init__(self, profile_name: str) -> None:
        super().__init__()
        self._profile_name = profile_name

    def compose(self) -> ComposeResult:
        logo_text = "\n".join(_LOGO)
        today = date.today().strftime("%Y.%m.%d")

        try:
            from majestic.display import _gather_startup
            d = _gather_startup(self._profile_name)
        except Exception:
            d = {}

        agent = d.get("agent_name", "Assistant")
        role  = d.get("role", "—")
        skill_count = d.get("skill_count", 0)
        mem_count   = d.get("mem_count", 0)
        lessons     = d.get("lessons_count", 0)
        api_ok      = d.get("api_ok", False)
        has_brave   = d.get("has_brave", False)

        api_str    = "[green]● ok[/green]" if api_ok else "[red]● missing[/red]"
        brave_str  = "[green]Brave[/green]" if has_brave else "[yellow]DuckDuckGo[/yellow]"

        info_lines = [
            f"  [dim]profile  ·[/dim] [#d95767]{self._profile_name}[/]",
            f"  [dim]agent    ·[/dim] [bold]{agent}[/bold]",
            f"  [dim]role     ·[/dim] {role[:38]}",
            f"  [dim]api      ·[/dim] {api_str}",
            f"  [dim]search   ·[/dim] {brave_str}",
            f"  [dim]skills   ·[/dim] {skill_count}",
            f"  [dim]memory   ·[/dim] {mem_count} tasks  ·  {lessons} lessons",
            f"  [dim]date     ·[/dim] {today}",
        ]

        with Vertical(id="banner-box"):
            yield Static(logo_text, id="banner-logo")
            yield Static("\n".join(info_lines), id="banner-info")
            yield Static("[dim]Press any key to continue…[/dim]", id="banner-hint")

    def on_mount(self) -> None:
        self.set_timer(2.0, self._close)

    def _close(self) -> None:
        self.app.pop_screen()

    def on_key(self, event) -> None:
        self.app.pop_screen()
