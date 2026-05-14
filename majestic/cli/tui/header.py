from datetime import date
from textual.widgets import Static


class MajesticHeader(Static):
    def __init__(self, profile_name: str, mode: str = "foreground") -> None:
        today = date.today().strftime("%Y.%m.%d")
        content = (
            f" [bold][#d95767]M A J E S T I C[/][/bold]"
            f"  [dim]·[/dim]  {profile_name}"
            f"  [dim]·[/dim]  {mode}"
            f"  [dim]·[/dim]  [dim]{today}[/dim]"
        )
        super().__init__(content)
