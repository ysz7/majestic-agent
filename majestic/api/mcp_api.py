"""MCP management API handlers."""
from __future__ import annotations


def handle_get_mcp_status() -> dict:
    from majestic import config as cfg
    servers = list(cfg.get("mcp_servers", []) or [])
    return {"servers": servers}


def handle_mcp_add(body: dict) -> dict:
    from majestic import config as cfg
    name    = (body.get("name") or "").strip()
    command = body.get("command") or []
    env     = body.get("env") or {}
    if not name or not command:
        return {"error": "name and command are required"}
    servers = list(cfg.get("mcp_servers", []) or [])
    servers = [s for s in servers if s.get("name") != name]
    entry: dict = {"name": name, "command": command}
    if env:
        entry["env"] = env
    servers.append(entry)
    cfg.set_value("mcp_servers", servers)
    return {"ok": True}


def handle_mcp_remove(name: str) -> dict:
    from majestic import config as cfg
    servers = [s for s in (cfg.get("mcp_servers", []) or []) if s.get("name") != name]
    cfg.set_value("mcp_servers", servers)
    return {"ok": True}


def handle_mcp_toggle(name: str) -> dict:
    from majestic import config as cfg
    servers = list(cfg.get("mcp_servers", []) or [])
    for s in servers:
        if s.get("name") == name:
            s["disabled"] = not s.get("disabled", False)
            break
    cfg.set_value("mcp_servers", servers)
    return {"ok": True}
