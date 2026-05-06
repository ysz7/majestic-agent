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


# ── Network presence ─────────────────────────────────────────────────────────

def announce_agent(port: int, role: str = "") -> None:
    """Called when API server starts — write role+URL into registry entry."""
    import atexit
    reg = read_registry()
    # Find which entry matches MAJESTIC_HOME (current agent)
    import os
    home_str = os.environ.get("MAJESTIC_HOME", str(_AGENTS_ROOT))
    for name, info in reg.items():
        if Path(info.get("home", "")).expanduser().resolve() == Path(home_str).expanduser().resolve():
            info["role"] = role
            info["url"]  = f"http://localhost:{port}"
            _write_registry(reg)
            atexit.register(deannounce_agent)
            return
    # Default agent not in registry — nothing to announce


def deannounce_agent() -> None:
    """Remove role/url from registry entry on shutdown."""
    import os
    reg = read_registry()
    home_str = os.environ.get("MAJESTIC_HOME", str(_AGENTS_ROOT))
    for info in reg.values():
        if Path(info.get("home", "")).expanduser().resolve() == Path(home_str).expanduser().resolve():
            info.pop("role", None)
            info.pop("url", None)
            _write_registry(reg)
            return


def find_agent_url(name_or_url: str) -> str | None:
    """Resolve a name from registry or return the URL if it's already an HTTP URL."""
    if name_or_url.startswith("http://") or name_or_url.startswith("https://"):
        return name_or_url
    reg = read_registry()
    entry = reg.get(name_or_url)
    if not entry:
        return None
    url = entry.get("url")
    if not url:
        port = entry.get("port")
        url = f"http://localhost:{port}" if port else None
    return url


def pick_delegate(task: str) -> str | None:
    """Keyword-match task against agent roles in delegates_to list. Returns name or URL."""
    try:
        from majestic.config import get
        delegates: list = get("agent.delegates_to", []) or []
    except Exception:
        return None
    if not delegates:
        return None
    reg = read_registry()
    task_words = set(task.lower().split())
    best_name, best_score = None, 0
    for target in delegates:
        if target.startswith("http"):
            continue
        role = (reg.get(target) or {}).get("role", "").lower()
        score = sum(1 for w in task_words if w in role)
        if score > best_score:
            best_score, best_name = score, target
    return best_name if best_score > 0 else None


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
