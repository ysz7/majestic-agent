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
  update           Update to the latest version from GitHub
  tools            Interactive tool checklist (enable/disable tools)
  tools list       Show available toolsets
  api start        Start REST API server (POST /chat, GET /health, GET /sessions)
  mcp list         List configured MCP servers and their tools
  mcp add NAME CMD Add MCP server (CMD is space-separated command)
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


def _migrate_exports_to_workspace() -> None:
    """One-time migration: move files from exports/ into workspace subfolders."""
    try:
        from majestic.constants import MAJESTIC_HOME, WORKSPACE_DIR
        exports = MAJESTIC_HOME / "exports"
        if not exports.exists():
            return
        _MAP = {
            "briefing_": "briefings", "predictions_": "briefings", "money_flows_": "briefings",
            "report_": "reports", "ideas_": "ideas",
        }
        for f in exports.glob("*.md"):
            dest_sub = next((v for k, v in _MAP.items() if f.name.startswith(k)), "reports")
            dest_dir = WORKSPACE_DIR / dest_sub
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f.name
            if not dest.exists():
                f.rename(dest)
        if not any(exports.iterdir()):
            exports.rmdir()
    except Exception:
        pass


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
    _migrate_exports_to_workspace()
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

    elif cmd == "update":
        _update_cmd()

    elif cmd == "api":
        _api_cmd(args[1:])

    elif cmd == "tools":
        _tools_cmd(args[1:])

    elif cmd == "mcp":
        _mcp_cmd(args[1:])

    elif cmd == "gateway":
        _gateway_cmd(args[1:])

    elif cmd is None:
        _launch_agent()

    else:
        print(f"Unknown command: {cmd}\n")
        print(_HELP)
        sys.exit(1)


def _tools_cmd(args: list[str]) -> None:
    from majestic import config as cfg
    from majestic.constants import CONFIG_FILE
    if not CONFIG_FILE.exists():
        from majestic.cli.display import warn
        warn("No configuration found. Run `majestic setup` first.\n")
        sys.exit(1)
    cfg.sync_env_from_config()

    sub = args[0] if args else ""
    if sub == "list":
        from majestic.tools.configurator import print_toolsets
        print_toolsets()
    else:
        from majestic.tools.configurator import run_configurator
        run_configurator()


def _mcp_cmd(args: list[str]) -> None:
    from majestic import config as cfg
    sub = args[0] if args else "list"

    if sub == "list":
        servers = cfg.get("mcp_servers", []) or []
        if not servers:
            print("  No MCP servers configured.")
            print("  Add one: majestic mcp add <name> <command...>")
            return
        cfg.sync_env_from_config()
        from majestic.mcp.bridge import load_all_servers, list_server_tools
        load_all_servers()
        loaded = list_server_tools()
        for srv in servers:
            name = srv.get("name", "?")
            tools = loaded.get(name, [])
            cmd_str = " ".join(srv.get("command", [])) or srv.get("url", "")
            print(f"\n  {name}  ({cmd_str})")
            if tools:
                for t in tools:
                    print(f"    · mcp_{name}_{t}")
            else:
                print(f"    (failed to connect or no tools)")
        print()

    elif sub == "add":
        if len(args) < 3:
            print("Usage: majestic mcp add <name> <command...>")
            sys.exit(1)
        name    = args[1]
        command = args[2:]
        servers = list(cfg.get("mcp_servers", []) or [])
        servers = [s for s in servers if s.get("name") != name]
        servers.append({"name": name, "command": command})
        cfg.set_value("mcp_servers", servers)
        print(f"  ✓ Added MCP server '{name}': {' '.join(command)}")

    elif sub == "remove":
        if len(args) < 2:
            print("Usage: majestic mcp remove <name>")
            sys.exit(1)
        name    = args[1]
        servers = [s for s in (cfg.get("mcp_servers", []) or []) if s.get("name") != name]
        cfg.set_value("mcp_servers", servers)
        print(f"  ✓ Removed MCP server '{name}'")

    else:
        print("Usage: majestic mcp <list|add|remove>")
        sys.exit(1)


def _api_cmd(args: list[str]) -> None:
    sub = args[0] if args else None
    if sub == "start":
        from majestic import config as cfg
        from majestic.constants import CONFIG_FILE
        if not CONFIG_FILE.exists():
            from majestic.cli.display import warn
            warn("No configuration found. Run `majestic setup` first.\n")
            sys.exit(1)
        cfg.sync_env_from_config()
        port = cfg.get("api.port", 8080)
        from majestic.api.server import start
        import time
        start(port=port)
        print("  Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            print("\n  Stopped.")
    else:
        print("Usage: majestic api <start>")
        sys.exit(1)


def _gateway_cmd(args: list[str]) -> None:
    sub     = args[0] if args else None
    target  = args[1] if len(args) > 1 else "all"

    if sub == "start":
        _gateway_start(target)
    elif sub == "setup":
        from majestic.cli.setup import gateway_setup
        gateway_setup()
    else:
        print("Usage: majestic gateway <start [telegram|discord|all]|setup>")
        sys.exit(1)


def _gateway_start(target: str = "all") -> None:
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
    from majestic.gateway.discord import DiscordPlatform
    from majestic.gateway.email_gw import EmailPlatform

    gw = Gateway()
    if target in ("telegram", "all"):
        gw.add(TelegramPlatform())
    if target in ("discord", "all"):
        gw.add(DiscordPlatform())
    if target in ("email", "all"):
        gw.add(EmailPlatform())

    asyncio.run(gw.run())


def _update_cmd() -> None:
    """Update majestic to the latest version via git stash → pull → stash pop."""
    import subprocess
    project_root = pathlib.Path(__file__).resolve().parent.parent.parent

    def _run(args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(args, cwd=project_root, capture_output=True, text=True)

    print("  Checking for updates...")

    # Verify this is a git repo
    if not (project_root / ".git").exists():
        print("  Not a git repository — cannot auto-update.")
        sys.exit(1)

    # Stash local changes if any
    status = _run(["git", "status", "--porcelain"])
    has_changes = bool(status.stdout.strip())
    if has_changes:
        print("  Stashing local changes...")
        _run(["git", "stash", "--include-untracked"])

    # Pull
    result = _run(["git", "pull", "--rebase"])
    if result.returncode != 0:
        print(f"  git pull failed:\n{result.stderr.strip()}")
        if has_changes:
            _run(["git", "stash", "pop"])
        sys.exit(1)

    # Restore stash
    if has_changes:
        print("  Restoring local changes...")
        pop = _run(["git", "stash", "pop"])
        if pop.returncode != 0:
            print(f"  Warning: stash pop had conflicts:\n{pop.stderr.strip()}")

    # Reinstall if pyproject.toml or requirements.txt changed
    changed = _run(["git", "diff", "HEAD@{1}", "--name-only"]).stdout
    needs_install = any(f in changed for f in ("pyproject.toml", "requirements.txt", "setup.py"))
    if needs_install:
        print("  Dependencies changed — running pip install...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-e", ".", "-q"], cwd=project_root)

    print("  Done. Majestic is up to date.")
