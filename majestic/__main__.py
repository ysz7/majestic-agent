"""
majestic.__main__
~~~~~~~~~~~~~~~~~
Entry point for the `majestic` CLI.  All sub-commands delegate to the
corresponding module under majestic/cli/.

Error handling:
  - Known errors (config, profile not found, no API key) → clean message + hint
  - Unexpected errors → short message + "run with --debug for details"
  - --debug flag → full traceback always shown
"""

from __future__ import annotations

import argparse
import sys
import traceback

_SUBCOMMANDS = {"setup", "new", "list", "rm", "run", "ps", "stop", "config", "model"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="majestic",
        description="Majestic — universal AI agent framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  majestic setup             — interactive first-run wizard\n"
            "  majestic new mybot         — scaffold a new agent profile\n"
            "  majestic config [mybot]    — edit agent configuration\n"
            "  majestic model             — change global LLM provider/model\n"
            "  majestic model mybot       — change model for a specific agent\n"
            "  majestic list              — list all profiles\n"
            "  majestic run mybot         — start mybot in the background\n"
            "  majestic ps               — show running agents\n"
            "  majestic stop mybot        — stop a running agent\n"
            "  majestic rm mybot          — delete a profile\n"
            "  majestic                   — launch the default profile (foreground)\n"
            "  majestic mybot             — launch mybot profile (foreground)\n"
        ),
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Show full tracebacks on error.",
    )

    parser.add_argument(
        "--tui",
        action="store_true",
        default=False,
        help="Launch the full split-screen TUI (default is plain CLI).",
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    sub.add_parser("setup", help="Interactive first-run wizard.")

    p_new = sub.add_parser("new", help="Scaffold a new agent profile.")
    p_new.add_argument("name", help="Profile name (alphanumeric + underscores).")

    sub.add_parser("list", help="List all available profiles.")

    p_rm = sub.add_parser("rm", help="Delete an agent profile and all its data.")
    p_rm.add_argument("name", help="Profile name to remove.")

    p_run = sub.add_parser("run", help="Start an agent profile as a background daemon.")
    p_run.add_argument("name", help="Profile name to run.")

    sub.add_parser("ps", help="List currently running agent daemons.")

    p_stop = sub.add_parser("stop", help="Stop a running agent daemon.")
    p_stop.add_argument("name", help="Profile name to stop.")

    p_config = sub.add_parser("config", help="Edit agent configuration interactively.")
    p_config.add_argument(
        "name",
        nargs="?",
        default="default",
        help="Profile name to configure (default: default).",
    )

    p_model = sub.add_parser("model", help="Change LLM provider or model.")
    p_model.add_argument(
        "name",
        nargs="?",
        default=None,
        help="Profile name to configure (omit for global settings).",
    )

    return parser


def _dispatch(command: str | None, args: argparse.Namespace, profile: str, tui: bool = False) -> None:  # noqa: FBT001
    """Route to the correct CLI module."""
    if command == "setup":
        from majestic.cli import setup as _setup
        _setup.run()

    elif command == "new":
        from majestic.cli import new as _new
        _new.run(args.name)

    elif command == "list":
        from majestic.cli import list_ as _list
        _list.run()

    elif command == "rm":
        from majestic.cli import rm as _rm
        _rm.run(args.name)

    elif command == "run":
        from majestic.cli import run_ as _run
        _run.run(args.name)

    elif command == "ps":
        from majestic.cli import ps as _ps
        _ps.run()

    elif command == "stop":
        from majestic.cli import stop as _stop
        _stop.run(args.name)

    elif command == "config":
        from majestic.cli import config as _config
        _config.run(getattr(args, "name", None) or "default")

    elif command == "model":
        from majestic.cli import model as _model
        _model.run(getattr(args, "name", None))

    else:
        from majestic.cli import foreground as _fg
        _fg.run(profile, tui=tui)


def main(argv: list[str] | None = None) -> None:
    raw = list(argv) if argv is not None else sys.argv[1:]

    # Separate --debug from the rest before argparse, so it doesn't interfere
    # with subcommand detection.
    debug = "--debug" in raw
    tui = "--tui" in raw
    if debug:
        raw = [a for a in raw if a != "--debug"]
    if tui:
        raw = [a for a in raw if a != "--tui"]

    # If the first non-flag token is not a known subcommand, treat the whole
    # invocation as a foreground profile launch (e.g. `majestic pain_hunter`).
    positional = [a for a in raw if not a.startswith("-")]
    first = positional[0] if positional else None

    if not raw:
        # No arguments → launch default profile in foreground.
        command = None
        args = argparse.Namespace(command=None, tui=tui)
        profile_name = "default"
    elif raw in (["--help"], ["-h"]):
        _build_parser().parse_args(raw)
        return
    elif first is not None and first not in _SUBCOMMANDS:
        # First token is not a known subcommand → treat as profile name.
        profile_name = first
        command = None
        args = argparse.Namespace(command=None, tui=tui)
    else:
        parser = _build_parser()
        args = parser.parse_args(raw)
        command = args.command
        profile_name = "default"

    try:
        _dispatch(command, args, profile_name, tui=tui)

    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)

    except FileNotFoundError as exc:
        print(f"\nError: {exc}")
        if debug:
            traceback.print_exc()
        sys.exit(1)

    except ValueError as exc:
        print(f"\nConfiguration error:\n{exc}")
        if debug:
            traceback.print_exc()
        sys.exit(1)

    except ImportError as exc:
        print(f"\nMissing dependency: {exc}")
        print("Try:  pip install -e .")
        if debug:
            traceback.print_exc()
        sys.exit(1)

    except Exception as exc:  # noqa: BLE001
        print(f"\nUnexpected error: {exc}")
        if debug:
            traceback.print_exc()
        else:
            print("Run with  --debug  for the full traceback.")
        sys.exit(1)


if __name__ == "__main__":
    main()
