import os

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
