from __future__ import annotations

import asyncio
import uuid

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual import work

from .messages import (
    AgentDone,
    AgentToken,
    BudgetUpdate,
    InfoEvent,
    SpinnerStart,
    SpinnerStop,
    TaskReport,
    ToolCallEvent,
    UserMessage,
)
from .banner_screen import BannerScreen
from .chat_pane import ChatPane
from .header import MajesticHeader
from .input_bar import InputBar
from .sidebar import Sidebar
from .status_bar import StatusBar


class MajesticApp(App):
    CSS = """
    Screen {
        layout: vertical;
        background: #1a1a1a;
    }
    MajesticHeader {
        height: 1;
        background: #2a1418;
        color: #d95767;
    }
    #main {
        layout: horizontal;
        height: 1fr;
    }
    ChatPane {
        width: 1fr;
        border-right: tall #2a2a2a;
        padding: 0 1;
    }
    Sidebar {
        width: 28;
        padding: 0 1;
    }
    StatusBar {
        height: 1;
        background: #222222;
        color: #666666;
    }
    InputBar {
        height: auto;
        min-height: 3;
        border-top: solid #2a2a2a;
    }
    #input-row {
        height: 3;
        layout: horizontal;
        padding: 1 1;
        align: left middle;
    }
    #prompt {
        width: 3;
        height: 1;
    }
    #main-input {
        width: 1fr;
        height: 1;
        border: none;
        background: transparent;
        color: white;
    }
    """

    BINDINGS = [
        ("ctrl+c", "interrupt", "Interrupt"),
        ("ctrl+q", "quit_app", "Quit"),
    ]

    def __init__(self, profile_name: str) -> None:
        super().__init__()
        self.profile_name = profile_name
        self._input_queue: asyncio.Queue[str | None] = asyncio.Queue()

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield MajesticHeader(self.profile_name)
        with Horizontal(id="main"):
            yield ChatPane(id="chat")
            yield Sidebar(self.profile_name, id="sidebar")
        yield StatusBar(id="status")
        yield InputBar(id="input_bar")

    def on_mount(self) -> None:
        self._install_display_hooks()
        self.push_screen(BannerScreen(self.profile_name))
        self._run_agent_loop()

    # ── Agent loop ────────────────────────────────────────────────────────────

    @work(exclusive=True, thread=False)
    async def _run_agent_loop(self) -> None:
        from majestic.config.settings import Settings
        from majestic.memory.working import WorkingMemory
        from majestic.core.gateway import Gateway
        from majestic.core.runtime import AgentRuntime
        from majestic.llm.router import LLMRouter
        from majestic.system.startup import StartupManager
        from majestic.cli.foreground import _register_tools

        try:
            settings = Settings(self.profile_name)
            settings.validate()
        except Exception as exc:
            self.post_message(InfoEvent(f"Config error: {exc}", "err"))
            return

        status = self.query_one(StatusBar)
        lim = settings.limits
        status._tokens_limit = lim.get("max_tokens_per_task", 0)
        status._cost_limit   = lim.get("max_cost_per_task", 0.0)

        working_memory = WorkingMemory()
        llm_router = LLMRouter(settings)
        startup = StartupManager(settings)

        try:
            incomplete = await startup.run()
            if incomplete:
                self.post_message(InfoEvent(
                    f"{len(incomplete)} incomplete task(s) from last session.", "warn"
                ))
        except Exception as exc:
            self.post_message(InfoEvent(f"Startup warning: {exc}", "warn"))

        gateway = Gateway(settings, working_memory, None)
        system_prompt = gateway.build_system_prompt()

        runtime = AgentRuntime(settings, working_memory, llm_router)
        runtime = _register_tools(runtime, settings)

        while True:
            text = await self._input_queue.get()
            if text is None:
                break

            working_memory.add_message("user", text)

            try:
                result = await runtime.run(task=text, system_prompt=system_prompt)
            except Exception as exc:
                result = f"Error: {exc}"

            self.post_message(AgentDone(result))
            working_memory.add_message("assistant", result)

    # ── Display hook installation ─────────────────────────────────────────────

    def _install_display_hooks(self) -> None:
        import majestic.display as d
        app = self

        class _TUISpinner:
            def __init__(self, text: str = "Thinking...") -> None:
                self.text = text

            def __enter__(self) -> "_TUISpinner":
                app.post_message(SpinnerStart(self.text))
                return self

            def __exit__(self, *_) -> None:
                app.post_message(SpinnerStop())

        d.Spinner            = _TUISpinner
        d.info               = lambda msg: app.post_message(InfoEvent(str(msg), "info"))
        d.ok                 = lambda msg: app.post_message(InfoEvent(str(msg), "ok"))
        d.warn               = lambda msg: app.post_message(InfoEvent(str(msg), "warn"))
        d.err                = lambda msg: app.post_message(InfoEvent(str(msg), "err"))
        d.reflection_start   = lambda: app.post_message(InfoEvent("Reflecting on task…", "info"))
        d.lesson_saved       = lambda l: app.post_message(InfoEvent(f"Lesson saved: {l[:56]}", "ok"))
        d.agent_delegating   = lambda t, p: app.post_message(InfoEvent(f"→ Delegating to {t}: {p[:40]}", "info"))
        d.agent_result       = lambda f: app.post_message(InfoEvent(f"← Result from {f}", "ok"))
        d.budget_warn        = lambda pct, kind, used, lim: app.post_message(
            InfoEvent(f"⚠ {pct}% of {kind} budget used ({used} / {lim})", "warn")
        )
        d.budget_exceeded    = lambda kind, used, lim: app.post_message(
            InfoEvent(f"✗ {kind} limit reached ({used} / {lim}). Task stopped.", "err")
        )
        d.task_report        = lambda steps, tokens, cost, elapsed: (
            app.post_message(TaskReport(steps, tokens, cost, elapsed)),
            app.post_message(BudgetUpdate(
                tokens,
                app.query_one(StatusBar)._tokens_limit,
                cost,
                app.query_one(StatusBar)._cost_limit,
            )),
        )

    # ── Message handlers ──────────────────────────────────────────────────────

    def on_input_bar_submitted(self, event: InputBar.Submitted) -> None:
        text = event.text.strip()
        if not text:
            return
        from .commands import handle_slash_command
        if text.startswith("/"):
            result = handle_slash_command(text, self)
            if result is not None:
                self.query_one(ChatPane).add_info(result, "info")
                return
        self.post_message(UserMessage(text))
        self._input_queue.put_nowait(text)

    def on_user_message(self, event: UserMessage) -> None:
        self.query_one(ChatPane).add_user_message(event.text)

    def on_agent_done(self, event: AgentDone) -> None:
        self.query_one(ChatPane).finish_agent_message(event.text)

    def on_agent_token(self, event: AgentToken) -> None:
        self.query_one(ChatPane).append_token(event.token)

    def on_tool_call_event(self, event: ToolCallEvent) -> None:
        self.query_one(ChatPane).add_tool_call(event.tool_name, event.args_preview)

    def on_info_event(self, event: InfoEvent) -> None:
        self.query_one(ChatPane).add_info(event.text, event.level)

    def on_spinner_start(self, event: SpinnerStart) -> None:
        self.query_one(StatusBar).set_thinking(event.text)

    def on_spinner_stop(self, event: SpinnerStop) -> None:
        self.query_one(StatusBar).set_idle()

    def on_budget_update(self, event: BudgetUpdate) -> None:
        self.query_one(StatusBar).update_budget(
            event.tokens, event.tokens_limit, event.cost, event.cost_limit
        )

    def on_task_report(self, event: TaskReport) -> None:
        self.query_one(ChatPane).add_task_report(
            event.steps, event.tokens, event.cost, event.elapsed
        )

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_interrupt(self) -> None:
        self.query_one(StatusBar).set_idle()
        self.query_one(ChatPane).add_info("Interrupted.", "warn")

    def action_quit_app(self) -> None:
        self._input_queue.put_nowait(None)
        self.exit()
