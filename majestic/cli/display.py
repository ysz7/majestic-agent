import os
import sys
import threading
import time

R   = "\033[0m"
B   = "\033[1m"
C   = "\033[38;2;217;87;103m"
G   = "\033[32m"
Y   = "\033[33m"
DIM = "\033[2m"
RED = "\033[31m"

_LINK = "\033]8;;https://github.com/ysz7/majestic-agent\033\\by ysz\033]8;;\033\\"

BANNER = f"""{C}{B}
  ██████╗   █████╗      ██╗███████╗███████╗████████╗██╗ ██████╗
  ██╔══██╗ ██╔══██╗     ██║██╔════╝██╔════╝╚══██╔══╝██║██╔════╝
  ██████╔╝ ███████║     ██║█████╗  ███████╗   ██║   ██║██║
  ██╔═══╝  ██╔══██║██   ██║██╔══╝  ╚════██║   ██║   ██║██║
  ██║      ██║  ██║╚█████╔╝███████╗███████║   ██║   ██║╚██████╗
  ╚═╝      ╚═╝  ╚═╝ ╚════╝ ╚══════╝╚══════╝   ╚═╝   ╚═╝ ╚═════╝
{R}{DIM}                               Universal Agent Executor  {_LINK}{R}
"""


class Spinner:
    """Animated terminal spinner. Swallows stdout from inner code."""
    _FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, text: str = "Thinking..."):
        self.text    = text
        self._stop   = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._real: object = None

    def _spin(self) -> None:
        i = 0
        while not self._stop.is_set():
            frame = self._FRAMES[i % len(self._FRAMES)]
            self._real.write(f"\r\033[2K\033[36m{frame}\033[0m {self.text}")  # type: ignore[attr-defined]
            self._real.flush()  # type: ignore[attr-defined]
            i += 1
            time.sleep(0.08)

    def __enter__(self) -> "Spinner":
        import io
        self._real = sys.__stdout__
        sys.stdout = io.StringIO()
        self._thread.start()
        return self

    def __exit__(self, *_) -> None:
        self._stop.set()
        self._thread.join()
        sys.stdout = self._real  # type: ignore[assignment]
        self._real.write("\r\033[2K")  # type: ignore[attr-defined]
        self._real.flush()  # type: ignore[attr-defined]


def print_banner() -> None:
    print(BANNER)


def print_status() -> None:
    from majestic import config as cfg

    provider = cfg.get("llm.provider", "anthropic")
    model    = cfg.get("llm.model", "—")

    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        llm_ok  = bool(api_key)
        dot     = f"{G}●{R}" if llm_ok else f"{RED}●{R}"
        label   = f"{dot} {DIM}anthropic / {model}{R}"
    elif provider == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        llm_ok  = bool(api_key)
        dot     = f"{G}●{R}" if llm_ok else f"{RED}●{R}"
        label   = f"{dot} {DIM}openrouter / {model}{R}"
    else:
        label = f"{DIM}{provider} / {model}{R}"

    home = os.environ.get("MAJESTIC_HOME", "~/.majestic-agent")
    print(f"  {label}   {DIM}home: {home}{R}\n")


def ok(msg: str) -> None:
    print(f"  {G}✓{R} {msg}")


def warn(msg: str) -> None:
    print(f"  {Y}⚠{R}  {msg}")


def err(msg: str) -> None:
    print(f"  {RED}✗{R} {msg}")


def info(msg: str) -> None:
    print(f"  {DIM}{msg}{R}")


def ask(prompt: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    try:
        val = input(f"  {B}{prompt}{hint}:{R} ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(0)
    return val or default


def choose(prompt: str, options: list[str], default: int = 0) -> int:
    print(f"\n  {B}{prompt}{R}")
    for i, opt in enumerate(options, 1):
        marker = f"{C}▶{R}" if i - 1 == default else " "
        print(f"  {marker} {i}. {opt}")
    raw = ask("Select", str(default + 1))
    try:
        idx = int(raw) - 1
        return idx if 0 <= idx < len(options) else default
    except ValueError:
        return default
