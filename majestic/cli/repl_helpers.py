"""CLI REPL helpers: spinner, agent runner, file ops. Commands are in repl_commands.py."""
from __future__ import annotations

import re
import threading
from pathlib import Path

from majestic.cli.display import R, B, C, G, Y, DIM, Spinner
import time as _time

_agent_stop = threading.Event()

SUPPORTED_EXTS = {".pdf", ".docx", ".csv", ".txt", ".md"}


def _friendly_error(exc: Exception) -> str:
    """Convert LLM / network exceptions to short human-readable messages."""
    name = type(exc).__name__
    msg = str(exc)
    # Anthropic SDK errors
    if "AuthenticationError" in name or "401" in msg:
        return "Invalid API key. Run `majestic setup` to reconfigure."
    if "PermissionDeniedError" in name or "403" in msg:
        return "API key doesn't have permission. Check your Anthropic plan."
    if "RateLimitError" in name or "429" in msg:
        return "Rate limit reached. Wait a moment and try again."
    if "APIStatusError" in name or "OverloadedError" in name or "529" in msg:
        return "Anthropic API is overloaded. Try again in a few seconds."
    if "APIConnectionError" in name or "Connection" in name:
        return "Cannot reach the API. Check your internet connection."
    if "BadRequestError" in name or "400" in msg:
        return f"Bad request: {msg[:120]}"
    # Generic fallback — show class + first line only (no traceback)
    first_line = msg.splitlines()[0][:120] if msg else name
    return f"{name}: {first_line}"

_SPIN_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

_active_spinner: "_LineSpinner | None" = None


def pause_active_spinner() -> None:
    if _active_spinner is not None:
        _active_spinner.pause()


def resume_active_spinner() -> None:
    if _active_spinner is not None:
        _active_spinner.resume()


class _LineSpinner:
    """Animates a single terminal line while a task runs, then finalizes it."""

    def __init__(self, out) -> None:
        self._out    = out
        self._stop   = threading.Event()
        self._paused = threading.Event()
        self._paused.set()
        self._wlock  = threading.Lock()   # serialises terminal writes — prevents race on pause
        self._line   = ""
        self._thread: threading.Thread | None = None

    def start(self, line: str) -> None:
        self.stop()
        self._line = line
        self._stop.clear()
        self._paused.set()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self._stop.set()
            self._thread.join(timeout=1.0)
            self._thread = None

    def pause(self) -> None:
        self._paused.clear()
        with self._wlock:  # wait for any in-flight frame write before clearing line
            self._out.write("\r\033[2K"); self._out.flush()

    def resume(self) -> None:
        self._paused.set()

    def _run(self) -> None:
        i = 0
        while not self._stop.wait(0.08):
            if self._paused.is_set():
                with self._wlock:
                    self._out.write(f"\r\033[2K{self._line} {DIM}{_SPIN_FRAMES[i % 10]}{R}")
                    self._out.flush()
                i += 1
        with self._wlock:
            self._out.write("\r\033[2K"); self._out.flush()


_ERR_DETAIL_MAX = 52


def _fmt_progress(line: str) -> str:
    low = line.lower()
    for kw in ("error:", "timeout —", "warning:"):
        idx = low.find(kw)
        if idx != -1:
            end    = idx + len(kw)
            detail = line[end:].strip()
            if len(detail) > _ERR_DETAIL_MAX:
                detail = detail[:_ERR_DETAIL_MAX] + "…"
            prefix = line[:end].strip()
            return f" {DIM}{prefix} {detail}{R}"
    return f" {DIM}{line.strip()}{R}"


class _SpinnerProxy:
    def __init__(self, real_out, spinner: _LineSpinner) -> None:
        self._real    = real_out
        self._spinner = spinner
        self._buf     = ""

    def write(self, data: str) -> int:
        self._buf += data
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.rstrip()
            if not line:
                continue
            self._spinner.pause()
            self._real.write(_fmt_progress(line) + "\n")
            self._real.flush()
            self._spinner.resume()
        return len(data)

    def flush(self) -> None: self._real.flush()
    def fileno(self) -> int: return self._real.fileno()


_TOOL_LABELS: dict[str, str] = {
    "search_knowledge":  "searching knowledge base",
    "search_web":        "searching web",
    "get_market_data":   "fetching market data",
    "run_research":      "collecting intel",
    "get_briefing":      "generating briefing",
    "get_news":          "fetching news",
    "get_report":        "generating report",
    "generate_ideas":    "generating ideas",
    "delegate_task":     "delegating sub-task",
    "delegate_parallel": "running parallel tasks",
    "read_file":         "reading file",
    "write_file":        "writing file",
    "run_command":       "running command",
    "workspace_list":    "listing workspace",
    "workspace_search":  "searching workspace",
    "workspace_delete":  "deleting file",
    "workspace_move":    "moving file",
}

_ARG_KEYS = ("query", "topic", "task", "prompt", "subject", "keyword", "text", "name", "path")
_LABEL_MAX = 32


def _tool_label(name: str, args: dict) -> str:
    base = _TOOL_LABELS.get(name, name.replace("_", " "))
    for key in _ARG_KEYS:
        val = (args.get(key) or "").strip()
        if val and isinstance(val, str) and len(val) >= 2:
            short = val[:_LABEL_MAX] + ("…" if len(val) > _LABEL_MAX else "")
            return f"{base} · {short}"
    return base


def run_agent(user_input: str, session_id: str | None, history: list) -> str:
    from majestic.agent.loop import AgentLoop
    import sys as _sys

    global _active_spinner
    _agent_stop.clear()
    _tools_used: list[str] = []
    _had_tools = [False]
    _start = _time.time()
    _spinner = _LineSpinner(_sys.__stdout__)
    _active_spinner = _spinner

    def _on_tool(name: str, _args: dict) -> None:
        _spinner.stop()
        _tools_used.append(name)
        prefix = f"{DIM}┌{R}" if not _had_tools[0] else f"{DIM}├{R}"
        _had_tools[0] = True
        _sys.__stdout__.write(f" {prefix} {C}{name}{R}\n")
        _sys.__stdout__.flush()
        label = _tool_label(name, _args)
        _spinner.start(f" {DIM}├ Working [{label}]{R}")

    loop = AgentLoop(stop_event=_agent_stop)
    _spinner.start(f" {DIM}· thinking...{R}")

    try:
        from majestic.token_tracker import get_stats as _gs
        _cost_before = _gs().get("cost_usd", 0.0)
    except Exception:
        _cost_before = 0.0

    _proxy = _SpinnerProxy(_sys.__stdout__, _spinner)
    _sys.stdout = _proxy
    try:
        result = loop.run(
            user_input,
            session_id=session_id,
            history=history,
            on_tool_call=_on_tool,
        )
    except KeyboardInterrupt:
        _sys.stdout = _sys.__stdout__
        _spinner.stop()
        _agent_stop.set()
        _sys.__stdout__.write("\r\033[2K")
        print(f"\n  {Y}Stopped.{R}\n")
        return ""
    except Exception as _e:
        _sys.stdout = _sys.__stdout__
        _spinner.stop()
        _sys.__stdout__.write("\r\033[2K")
        _err_msg = _friendly_error(_e)
        print(f"\n  {Y}✗ {_err_msg}{R}\n")
        return ""
    finally:
        _sys.stdout = _sys.__stdout__

    _spinner.stop()

    elapsed = _time.time() - _start
    try:
        from majestic.token_tracker import get_stats as _gs
        cost = max(0.0, _gs().get("cost_usd", 0.0) - _cost_before)
    except Exception:
        cost = 0.0

    n = len(_tools_used)
    if n > 0:
        calls = f"{n} tool call{'s' if n != 1 else ''}"
        _sys.__stdout__.write(f" {DIM}└ Done{R} {DIM}· {calls} · ${cost:.4f} · {elapsed:.1f}s{R}\n")
        _sys.__stdout__.flush()

    _active_spinner = None
    _print_answer(result)
    answer = result.get("answer", "")

    if len(set(_tools_used)) >= 2 and answer:
        try:
            from majestic.skills.creator import suggest_skill
            from majestic import config as _cfg
            suggest_skill(user_input, answer[:500], _tools_used, lang=_cfg.get("language", "EN"))
        except Exception:
            pass

    return answer


def _print_answer(result: dict) -> None:
    from majestic.gateway.formatter import print_cli
    print_cli(result.get("answer", "") or "")


def dispatch_shortcut(cmd: str, rest: str) -> None:
    from majestic.cli.commands import dispatch
    import sys as _sys

    args: dict = {}
    if cmd == "briefing" and rest:
        try:
            args["days"] = int(rest.split()[0])
        except ValueError:
            pass
    elif cmd == "news" and rest:
        try:
            args["limit"] = int(rest.split()[0])
        except ValueError:
            pass
    elif cmd == "report":
        args["topic"] = rest

    spinner = _LineSpinner(_sys.__stdout__)
    _sys.__stdout__.write(f" {DIM}┌{R} {C}{cmd}{R}\n")
    _sys.__stdout__.flush()
    label = _TOOL_LABELS.get(cmd, cmd.replace("_", " "))
    if args.get("topic"):
        short = args["topic"][:_LABEL_MAX] + ("…" if len(args["topic"]) > _LABEL_MAX else "")
        label = f"{label} · {short}"
    spinner.start(f" {DIM}├ Working [{label}]{R}")

    try:
        from majestic.token_tracker import get_stats as _gs
        _cost_before = _gs().get("cost_usd", 0.0)
    except Exception:
        _cost_before = 0.0

    _proxy = _SpinnerProxy(_sys.__stdout__, spinner)
    _old_stdout = _sys.stdout
    _sys.stdout = _proxy
    _start = _time.time()
    try:
        result = dispatch(cmd, args)
    finally:
        _sys.stdout = _old_stdout
    elapsed = _time.time() - _start

    spinner.stop()

    try:
        from majestic.token_tracker import get_stats as _gs
        cost = max(0.0, _gs().get("cost_usd", 0.0) - _cost_before)
    except Exception:
        cost = 0.0

    _sys.__stdout__.write(f" {DIM}└ Done{R} {DIM}· ${cost:.4f} · {elapsed:.1f}s{R}\n")
    _sys.__stdout__.flush()

    try:
        from majestic.gateway.formatter import print_cli
        print_cli(result)
    except Exception:
        print(f"\n{result}\n")


def looks_like_path(text: str) -> bool:
    return len(split_paths(text.strip())) > 0


def split_paths(text: str) -> list[Path]:
    tokens = re.findall(r'"[^"]*"|\'[^\']*\'|\S+', text)
    paths = []
    for token in tokens:
        p = Path(token.strip("'\"").replace("\\", "/")).expanduser()
        if p.exists() and p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            paths.append(p)
    return paths


def handle_files(paths: list[Path]) -> None:
    import majestic.tools as _tools
    for p in paths:
        size_kb = p.stat().st_size / 1024
        size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb / 1024:.1f} MB"
        print(f"\n  📄 {p.name} ({size_str}) — index? [Enter / n] ", end="", flush=True)
        if input().strip().lower() == "n":
            continue
        with Spinner(f"Indexing {p.name}..."):
            _tools.execute("index_file", {"path": str(p)})
        print(f"  {G}✓ Indexed {p.name}{R}\n")
