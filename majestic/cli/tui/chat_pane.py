from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Static


class ChatPane(Widget):
    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="chat-scroll")

    def on_mount(self) -> None:
        self._current_agent_widget: Static | None = None
        self._current_agent_text: str = ""
        # Welcome message
        self._add_widget(Static(
            "  [#d95767]Agent:[/]  Ready. Type your message or [bold]/help[/bold] for commands.\n",
            classes="agent-msg",
        ))

    # ── Public API ────────────────────────────────────────────────────────────

    def add_user_message(self, text: str) -> None:
        self._flush_stream()
        self._add_widget(Static(
            f"\n  [bold white]You:[/]  {text}\n",
            classes="user-msg",
        ))
        # Placeholder for the upcoming agent reply (filled by stream or done)
        self._current_agent_text = ""
        self._current_agent_widget = Static(
            "  [#d95767]Agent:[/]  [dim]…[/dim]",
            classes="agent-msg streaming",
        )
        self._add_widget(self._current_agent_widget)

    def append_token(self, token: str) -> None:
        self._current_agent_text += token
        if self._current_agent_widget:
            self._current_agent_widget.update(
                f"  [#d95767]Agent:[/]  {self._current_agent_text}"
            )
            self._scroll_bottom()

    def finish_agent_message(self, text: str) -> None:
        if self._current_agent_widget:
            self._current_agent_widget.update(
                f"  [#d95767]Agent:[/]  {text}\n"
            )
            self._current_agent_widget.remove_class("streaming")
            self._current_agent_widget = None
            self._current_agent_text = ""
        else:
            self._add_widget(Static(
                f"\n  [#d95767]Agent:[/]  {text}\n",
                classes="agent-msg",
            ))
        self._scroll_bottom()

    def add_tool_call(self, tool_name: str, args_preview: str = "") -> None:
        args = f" [dim]{args_preview[:48]}[/dim]" if args_preview else ""
        self._add_widget(Static(
            f"    [cyan]● {tool_name}[/cyan]{args}",
            classes="tool-msg",
        ))

    def add_info(self, text: str, level: str = "info") -> None:
        color = {"info": "dim", "ok": "green", "warn": "yellow", "err": "red"}.get(level, "dim")
        self._add_widget(Static(
            f"    [{color}]{text}[/]",
            classes="info-msg",
        ))

    def add_task_report(self, steps: int, tokens: int, cost: float, elapsed: float) -> None:
        line = f"  [dim]{'─' * 52}[/dim]"
        stats = (
            f"  [dim]steps {steps}  ·  tokens {tokens:,}  ·  "
            f"cost ${cost:.4f}  ·  {elapsed:.1f}s[/dim]"
        )
        self._add_widget(Static(f"{line}\n{stats}\n{line}\n", classes="report-msg"))

    # ── Internal ──────────────────────────────────────────────────────────────

    def _add_widget(self, w: Static) -> None:
        self.query_one("#chat-scroll").mount(w)
        self._scroll_bottom()

    def _flush_stream(self) -> None:
        if self._current_agent_widget and self._current_agent_text:
            self._current_agent_widget.remove_class("streaming")
            self._current_agent_widget = None
            self._current_agent_text = ""

    def _scroll_bottom(self) -> None:
        self.query_one(VerticalScroll).scroll_end(animate=False)
