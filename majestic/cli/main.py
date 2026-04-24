"""
Entry point for the `majestic` command.

  majestic              — launch agent REPL
  majestic setup        — first-run configuration wizard
  majestic model        — switch LLM provider/model
  majestic config       — show / get / set config values
  majestic doctor       — diagnose configuration
"""
import sys

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

  --version        Show version
"""


def _launch_agent() -> None:
    from majestic import config as cfg
    from majestic.constants import CONFIG_FILE

    if not CONFIG_FILE.exists():
        from majestic.cli.display import warn
        warn("No configuration found. Running setup first...\n")
        from majestic.cli.setup import run_setup
        run_setup()
        return

    # Sync env vars so legacy core/ code picks up config from MAJESTIC_HOME
    cfg.sync_env_from_config()

    # Phase 0: delegate to existing CLI until Phase 4 (agentic loop)
    import sys
    import os
    from pathlib import Path
    project_root = Path(__file__).parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # Point existing code at project-local data/ for now
    # (Phase 1 migrates storage to MAJESTIC_HOME/state.db)
    from cli import main as cli_main
    cli_main()


def main() -> None:
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

    elif cmd is None:
        _launch_agent()

    else:
        print(f"Unknown command: {cmd}\n")
        print(_HELP)
        sys.exit(1)
