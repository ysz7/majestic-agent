"""
Entry point for the `majestic` command.

  majestic              — launch agent REPL
  majestic setup        — first-run configuration wizard
  majestic model        — switch LLM provider/model
  majestic config       — show / get / set config values
  majestic doctor       — diagnose configuration
  majestic gateway      — manage platform gateway (Telegram, …)
"""
import os
import sys
import pathlib

_HELP = """\
Usage: majestic [command]

Commands:
  (none)           Launch agent
  setup            First-run configuration wizard
  model            Switch LLM provider/model
  config           Show current config
  config get KEY   Get a config value  (e.g. config get llm.provider)
  config set KEY V Set a config value  (e.g. config set language RU)
  doctor           Diagnose configuration problems
  gateway start    Start gateway (Telegram + any configured platform)
  gateway setup    Configure platform connections interactively

  --version        Show version
"""


def _reexec_with_venv_if_needed() -> None:
    """Re-exec with venv Python if the current interpreter is not from the project venv."""
    project_root = pathlib.Path(__file__).resolve().parent.parent.parent
    venv_dir = project_root / ".venv"
    if not venv_dir.exists():
        return
    # Use sys.prefix (not executable) — venv Python symlinks to the same binary as system Python
    if pathlib.Path(sys.prefix).resolve() == venv_dir.resolve():
        return
    venv_python = venv_dir / "bin" / "python3"
    if not venv_python.exists():
        return
    os.execv(str(venv_python), [str(venv_python)] + sys.argv)


def _launch_agent() -> None:
    from majestic import config as cfg
    from majestic.constants import CONFIG_FILE

    if not CONFIG_FILE.exists():
        from majestic.cli.display import warn
        warn("No configuration found. Running setup first...\n")
        from majestic.cli.setup import run_setup
        run_setup()
        return

    cfg.sync_env_from_config()
    from majestic.cli.repl import run
    run()


def main() -> None:
    _reexec_with_venv_if_needed()
    args = sys.argv[1:]
    cmd  = args[0] if args else None

    if cmd in ("--version", "-v"):
        from importlib.metadata import version, PackageNotFoundError
        try:
            print(f"majestic {version('majestic-agent')}")
        except PackageNotFoundError:
            print("majestic 0.1.0-dev")

    elif cmd in ("--help", "-h", "help", None) and cmd != None:
        print(_HELP)

    elif cmd == "setup":
        from majestic.cli.setup import run_setup
        run_setup()

    elif cmd == "model":
        from majestic.cli.setup import select_model
        select_model()

    elif cmd == "config":
        from majestic.cli.setup import config_cmd
        config_cmd(args[1:])

    elif cmd == "doctor":
        from majestic.cli.setup import run_doctor
        run_doctor()

    elif cmd == "gateway":
        _gateway_cmd(args[1:])

    elif cmd is None:
        _launch_agent()

    else:
        print(f"Unknown command: {cmd}\n")
        print(_HELP)
        sys.exit(1)


def _gateway_cmd(args: list[str]) -> None:
    sub = args[0] if args else None

    if sub == "start":
        _gateway_start()
    elif sub == "setup":
        from majestic.cli.setup import gateway_setup
        gateway_setup()
    else:
        print("Usage: majestic gateway <start|setup>")
        sys.exit(1)


def _gateway_start() -> None:
    import asyncio
    from majestic import config as cfg
    from majestic.constants import CONFIG_FILE

    if not CONFIG_FILE.exists():
        from majestic.cli.display import warn
        warn("No configuration found. Run `majestic setup` first.\n")
        sys.exit(1)

    cfg.sync_env_from_config()

    from majestic.gateway.health import start as start_health
    start_health()

    from majestic.gateway import Gateway
    from majestic.gateway.telegram import TelegramPlatform

    gw = Gateway()
    gw.add(TelegramPlatform())

    asyncio.run(gw.run())
