"""
majestic.__main__
~~~~~~~~~~~~~~~~~
Entry point for the `majestic` CLI.  All sub-commands delegate to the
corresponding module under majestic/cli/.
"""

import argparse
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="majestic",
        description="Majestic — universal AI agent framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  majestic setup             — interactive first-run wizard\n"
            "  majestic new mybot         — scaffold a new agent profile\n"
            "  majestic list              — list all profiles\n"
            "  majestic run mybot         — start mybot in the background\n"
            "  majestic ps               — show running agents\n"
            "  majestic stop mybot        — stop a running agent\n"
            "  majestic rm mybot          — delete a profile\n"
            "  majestic                   — launch the default profile (foreground)\n"
            "  majestic mybot             — launch mybot profile (foreground)\n"
        ),
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")

    # setup
    sub.add_parser(
        "setup",
        help="Interactive first-run wizard: create directories, check dependencies.",
    )

    # new <name>
    p_new = sub.add_parser("new", help="Scaffold a new agent profile.")
    p_new.add_argument("name", help="Profile name (alphanumeric + underscores).")

    # list
    sub.add_parser("list", help="List all available profiles.")

    # rm <name>
    p_rm = sub.add_parser("rm", help="Delete an agent profile and all its data.")
    p_rm.add_argument("name", help="Profile name to remove.")

    # run <name>
    p_run = sub.add_parser("run", help="Start an agent profile as a background daemon.")
    p_run.add_argument("name", help="Profile name to run.")

    # ps
    sub.add_parser("ps", help="List currently running agent daemons.")

    # stop <name>
    p_stop = sub.add_parser("stop", help="Stop a running agent daemon.")
    p_stop.add_argument("name", help="Profile name to stop.")

    # positional profile (foreground, optional)
    parser.add_argument(
        "profile",
        nargs="?",
        default=None,
        metavar="<profile>",
        help=(
            "Run this profile in the foreground (interactive session). "
            'Defaults to "default" when omitted.'
        ),
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    command = args.command

    # ------------------------------------------------------------------ #
    # Named sub-commands                                                   #
    # ------------------------------------------------------------------ #
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

    else:
        # No recognised sub-command — treat as foreground profile launch.
        # If the user typed `majestic some_profile`, argparse stores it in
        # args.profile; if they typed nothing it is None → "default".
        profile_name = args.profile or "default"
        from majestic.cli import foreground as _fg
        _fg.run(profile_name)


if __name__ == "__main__":
    main()
