from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, Static

from .commands import SLASH_COMMANDS


class AutocompleteList(Widget):
    """Slash-command suggestions — no backgrounds, color only."""

    DEFAULT_CSS = """
    AutocompleteList {
        display: none;
        height: auto;
        padding: 0 2;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._items: list[str] = []
        self._cursor: int = 0

    # ── Public ───────────────────────────────────────────────────────────────

    def show(self, items: list[str]) -> None:
        self._items = items
        self._cursor = 0
        self.display = bool(items)
        self.refresh(layout=True)

    def hide(self) -> None:
        self._items = []
        self.display = False

    def move(self, delta: int) -> None:
        if self._items:
            self._cursor = (self._cursor + delta) % len(self._items)
            self.refresh()

    @property
    def selected(self) -> str | None:
        return self._items[self._cursor] if self._items else None

    # ── Render ────────────────────────────────────────────────────────────────

    def render(self) -> Text:
        text = Text()
        for i, cmd in enumerate(self._items):
            desc = SLASH_COMMANDS.get(cmd, "")
            if i == self._cursor:
                text.append(f" {cmd}", style="bold #d95767")
            else:
                text.append(f" {cmd}", style="#666666")
            if desc:
                text.append(f"  {desc}", style="dim")
            if i < len(self._items) - 1:
                text.append("\n")
        return text


class InputBar(Widget):
    class Submitted(Message):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._history: list[str] = []
        self._history_pos: int = -1

    def compose(self) -> ComposeResult:
        yield AutocompleteList(id="autocomplete-list")
        with Horizontal(id="input-row"):
            yield Static("[#d95767 bold]>[/] ", id="prompt")
            yield Input(placeholder="Type a message or /command…", id="main-input")

    def on_mount(self) -> None:
        self.query_one("#main-input", Input).focus()

    # ── Input events ─────────────────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        ac = self.query_one(AutocompleteList)
        if ac.display and ac.selected:
            text = ac.selected
            ac.hide()
            self.query_one(Input).value = ""
        else:
            text = event.value.strip()
        if not text:
            return
        self._history.append(text)
        self._history_pos = -1
        self.query_one(Input).clear()
        self.post_message(self.Submitted(text))

    def on_input_changed(self, event: Input.Changed) -> None:
        val = event.value
        ac = self.query_one(AutocompleteList)
        if val.startswith("/"):
            matches = [c for c in SLASH_COMMANDS if c.lower().startswith(val.lower())]
            ac.show(matches) if matches else ac.hide()
        else:
            ac.hide()

    def on_key(self, event) -> None:
        key = event.key
        inp = self.query_one(Input)
        ac = self.query_one(AutocompleteList)

        if key == "up":
            if ac.display:
                ac.move(-1)
                event.prevent_default()
            elif self._history:
                self._history_pos = min(self._history_pos + 1, len(self._history) - 1)
                inp.value = self._history[-(self._history_pos + 1)]
                inp.cursor_position = len(inp.value)
                event.prevent_default()

        elif key == "down":
            if ac.display:
                ac.move(1)
                event.prevent_default()
            elif self._history_pos >= 0:
                self._history_pos -= 1
                if self._history_pos >= 0:
                    inp.value = self._history[-(self._history_pos + 1)]
                else:
                    inp.clear()
                inp.cursor_position = len(inp.value)
                event.prevent_default()

        elif key == "tab":
            if ac.display and ac.selected:
                inp.value = ac.selected + " "
                inp.cursor_position = len(inp.value)
                ac.hide()
                event.prevent_default()

        elif key == "enter":
            if ac.display and ac.selected:
                text = ac.selected
                ac.hide()
                inp.value = ""
                self._history.append(text)
                self._history_pos = -1
                self.post_message(self.Submitted(text))
                event.prevent_default()

        elif key == "escape":
            if ac.display:
                ac.hide()
                event.prevent_default()
