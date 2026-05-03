"""
Entry point for the `majestic` command.

  majestic              — launch agent REPL
  majestic setup        — first-run configuration wizard
  majestic model        — switch LLM provider/model
  majestic config       — show / get / set config values
  majestic doctor       — diagnose configuration
  majestic gateway      — manage platform gateway (Telegram, …)
  majestic dashboard    — start web dashboard (API + React frontend)
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
  dashboard        Start web dashboard (serves React UI + REST API)
  mcp list              List configured MCP servers and their tools
  mcp add NAME CMD      Add MCP server (CMD is space-separated command)
  mcp install PRESET    Install preset: browser, github, postgres
  gateway start [platform]   Start gateway (telegram|discord|email|all)
  gateway setup [platform]   Configure a specific platform (writes only to .env)

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

    elif cmd == "dashboard":
        _dashboard_cmd(args[1:])

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

    elif sub == "install":
        _mcp_install(args[1] if len(args) > 1 else "")

    else:
        print("Usage: majestic mcp <list|add|remove|install>")
        sys.exit(1)


_MCP_PRESETS: dict[str, dict] = {
    "browser": {
        "name": "browser",
        "command": ["npx", "-y", "@playwright/mcp"],
        "description": "Playwright browser — screenshots, JS-heavy pages, web automation",
    },
    "github": {
        "name": "github",
        "command": ["npx", "-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"},
        "description": "GitHub — repos, issues, PRs, code search",
        "env_hint": "Requires GITHUB_TOKEN environment variable",
    },
    "postgres": {
        "name": "postgres",
        "command": ["npx", "-y", "@modelcontextprotocol/server-postgres", "${DATABASE_URL}"],
        "description": "PostgreSQL — SQL queries, schema inspection",
        "env_hint": "Requires DATABASE_URL environment variable",
    },
}


def _mcp_install(preset: str) -> None:
    import subprocess
    if not preset or preset not in _MCP_PRESETS:
        print("Available presets: browser, github, postgres")
        print("Usage: majestic mcp install <browser|github|postgres>")
        sys.exit(1)

    # Check npx available
    r = subprocess.run(["npx", "--version"], capture_output=True, text=True)
    if r.returncode != 0:
        print("  ✗ npx not found. Install Node.js first: https://nodejs.org")
        sys.exit(1)

    from majestic import config as cfg
    p = _MCP_PRESETS[preset]
    servers = list(cfg.get("mcp_servers", []) or [])
    if any(s.get("name") == p["name"] for s in servers):
        print(f"  MCP server '{preset}' is already configured.")
        return

    entry: dict = {"name": p["name"], "command": p["command"]}
    if "env" in p:
        entry["env"] = p["env"]
    servers.append(entry)
    cfg.set_value("mcp_servers", servers)
    print(f"  ✓ Added MCP server '{preset}': {' '.join(p['command'])}")
    if "env_hint" in p:
        print(f"  ⚠  {p['env_hint']}")


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
        gateway_setup(platform=target)
    else:
        print("Usage: majestic gateway <start|setup> [telegram|discord|email|all]")
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


def _dashboard_cmd(args: list[str]) -> None:
    """Start the web dashboard: REST API + serve built React frontend."""
    import subprocess
    import time
    import webbrowser

    from majestic import config as cfg
    from majestic.constants import CONFIG_FILE

    build_only = "--build" in args
    dev_mode   = "--dev" in args

    # --port <N>
    port = 8090
    if "--port" in args:
        idx = args.index("--port")
        if idx + 1 < len(args):
            port = int(args[idx + 1])

    project_root  = pathlib.Path(__file__).resolve().parent.parent.parent
    dashboard_dir = project_root / "dashboard"

    if build_only:
        _dashboard_build(dashboard_dir, project_root)
        return

    if dev_mode:
        _dashboard_dev(dashboard_dir, port)
        return

    # Normal: serve built static + API
    static_dir = project_root / "majestic" / "api" / "static"
    if not static_dir.exists():
        print("  Static build not found — building first…")
        _dashboard_build(dashboard_dir, project_root)

    if not CONFIG_FILE.exists():
        from majestic.cli.display import warn
        warn("No config yet — open the browser to complete setup.\n")
    else:
        cfg.sync_env_from_config()

    saved_port = cfg.get("dashboard.port", None)
    if saved_port and "--port" not in args:
        port = int(saved_port)

    from majestic.api.server import start
    print(f"  Dashboard at http://localhost:{port}")
    print("  Press Ctrl+C to stop.")
    start(port=port)
    _wait_for_server(port)
    try:
        webbrowser.open(f"http://localhost:{port}")
    except Exception:
        pass
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\n  Stopped.")


def _wait_for_server(port: int, timeout: float = 5.0) -> None:
    """Block until the server accepts connections or timeout expires."""
    import urllib.request
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(f"http://localhost:{port}/health", timeout=0.3)
            return
        except Exception:
            time.sleep(0.1)


def _dashboard_build(dashboard_dir: pathlib.Path, project_root: pathlib.Path) -> None:
    import subprocess
    import shutil
    if not dashboard_dir.exists():
        print("  dashboard/ directory not found.")
        sys.exit(1)
    node = subprocess.run(["node", "--version"], capture_output=True, text=True)
    if node.returncode != 0:
        _prompt_install_node()
        sys.exit(1)
    print("  Building dashboard…")
    result = subprocess.run(["npm", "run", "build"], cwd=dashboard_dir, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr[-2000:])
        sys.exit(1)
    static_dir = project_root / "majestic" / "api" / "static"
    if static_dir.exists():
        shutil.rmtree(static_dir)
    shutil.copytree(dashboard_dir / "dist", static_dir)
    print(f"  ✓ Built → {static_dir}")


def _dashboard_dev(dashboard_dir: pathlib.Path, api_port: int) -> None:
    """Run Vite dev server (HMR) alongside the API server."""
    import subprocess
    import time
    import webbrowser
    if not dashboard_dir.exists():
        print("  dashboard/ directory not found.")
        sys.exit(1)
    from majestic import config as cfg
    from majestic.constants import CONFIG_FILE
    if CONFIG_FILE.exists():
        cfg.sync_env_from_config()
    vite_port = 5173
    from majestic.api.server import start
    start(port=api_port)
    vite_proc = subprocess.Popen(
        ["npm", "run", "dev", "--", "--port", str(vite_port)],
        cwd=dashboard_dir,
    )
    url = f"http://localhost:{vite_port}"
    print(f"  Vite dev server at {url}")
    print(f"  API server at http://localhost:{api_port}")
    print("  Press Ctrl+C to stop.")
    _wait_for_server(api_port)
    _wait_for_server(vite_port, timeout=15.0)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        vite_proc.terminate()
        print("\n  Stopped.")


def _prompt_install_node() -> None:
    """Ask user to install Node.js (needed for dashboard build)."""
    print("  Node.js is not installed, but it is required to build the dashboard.")
    print("  Would you like to install it now? [y/N] ", end="", flush=True)
    answer = input().strip().lower()
    if answer not in ("y", "yes"):
        print("  Skipped. Install Node.js from https://nodejs.org and re-run.")
        return
    import subprocess
    import platform
    plat = platform.system()
    if plat == "Linux":
        r = subprocess.run(
            ["bash", "-c", "curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash - && sudo apt-get install -y nodejs"],
            check=False,
        )
        if r.returncode != 0:
            print("  Auto-install failed. Please install Node.js manually: https://nodejs.org")
    elif plat == "Darwin":
        r = subprocess.run(["brew", "install", "node"], check=False)
        if r.returncode != 0:
            print("  Auto-install failed. Please install Node.js manually: https://nodejs.org")
    else:
        print("  Auto-install not supported on this platform. Please install manually: https://nodejs.org")


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
