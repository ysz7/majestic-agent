"""Named agent registry — create, list, and resolve multi-instance agents."""
import json
import re
import socket
from pathlib import Path

_AGENTS_ROOT   = Path("~/.majestic-agent").expanduser()
_REGISTRY_FILE = _AGENTS_ROOT / ".registry.json"
_DEFAULT_PORT  = 8080


# ── Registry I/O ─────────────────────────────────────────────────────────────

def read_registry() -> dict:
    try:
        return json.loads(_REGISTRY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_registry(reg: dict) -> None:
    _AGENTS_ROOT.mkdir(parents=True, exist_ok=True)
    _REGISTRY_FILE.write_text(json.dumps(reg, indent=2), encoding="utf-8")


# ── Public API ────────────────────────────────────────────────────────────────

def known_names() -> set[str]:
    return set(read_registry().keys())


def resolve_home(name: str) -> Path | None:
    reg = read_registry()
    entry = reg.get(name)
    return Path(entry["home"]) if entry else None


def resolve_port(name: str) -> int:
    reg = read_registry()
    entry = reg.get(name)
    return int(entry["port"]) if entry and "port" in entry else _DEFAULT_PORT


def init_agent(name: str) -> None:
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
        print(f"  Invalid name '{name}'. Use letters, digits, underscores (no spaces).")
        return
    reg = read_registry()
    if name in reg:
        home = Path(reg[name]["home"])
        print(f"  Agent '{name}' already exists → {home}")
        return
    port = _next_free_port(reg)
    home = _AGENTS_ROOT / name
    home.mkdir(parents=True, exist_ok=True)
    reg[name] = {"home": str(home), "port": port}
    _write_registry(reg)
    print(f"  ✓ Created '{name}' → {home}  (port {port})")
    print(f"  Next:  majestic {name} setup   # configure API keys and model")
    print(f"  Then:  majestic {name}         # launch")


def list_agents() -> None:
    reg  = read_registry()
    rows = [("(default)", str(_AGENTS_ROOT), _DEFAULT_PORT)]
    for n, info in sorted(reg.items()):
        rows.append((n, info.get("home", ""), int(info.get("port", _DEFAULT_PORT))))

    name_w = max(len(r[0]) for r in rows)
    print()
    for name, home, port in rows:
        status = "●" if _port_listening(port) else "○"
        print(f"  {status}  {name:<{name_w}}  :{port}  {home}")
    print()


def ps_agents() -> None:
    reg  = read_registry()
    rows = [("(default)", str(_AGENTS_ROOT), _DEFAULT_PORT)]
    for n, info in sorted(reg.items()):
        rows.append((n, info.get("home", ""), int(info.get("port", _DEFAULT_PORT))))

    running = [(n, h, p) for n, h, p in rows if _port_listening(p)]
    if not running:
        print("  No agents running.")
        return
    name_w = max(len(r[0]) for r in running)
    print()
    for name, home, port in running:
        print(f"  ●  {name:<{name_w}}  :{port}  {home}")
    print()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _next_free_port(reg: dict) -> int:
    used = {_DEFAULT_PORT} | {int(v["port"]) for v in reg.values() if "port" in v}
    port = _DEFAULT_PORT + 1
    while port in used:
        port += 1
    return port


def _port_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.1)
        return s.connect_ex(("127.0.0.1", port)) == 0
