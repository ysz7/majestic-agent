"""
MCP bridge — reads mcp_servers from config, starts clients, registers their tools
in Majestic's tool registry with prefix mcp_{server}_{tool}.

Called once at agent startup from majestic/tools/__init__.py.
"""
from __future__ import annotations

from .client import StdioMCPClient

_clients: dict[str, StdioMCPClient] = {}


def load_all_servers() -> int:
    """Start all configured MCP servers and register their tools. Returns count of tools loaded."""
    try:
        from majestic import config as _cfg
        servers = _cfg.get("mcp_servers", []) or []
    except Exception:
        return 0

    total = 0
    for srv in servers:
        name = srv.get("name", "")
        if not name:
            continue
        if "url" in srv:
            continue  # SSE transport not yet supported
        command = srv.get("command", [])
        if not command:
            continue
        env = srv.get("env", {})
        try:
            total += _load_server(name, command, env)
        except Exception as e:
            import sys
            print(f"  [MCP] Failed to start '{name}': {e}", file=sys.stderr)
    return total


def _load_server(name: str, command: list[str], env: dict) -> int:
    client = StdioMCPClient(name=name, command=command, env=env)
    client.start()
    tools = client.list_tools()
    _clients[name] = client

    from majestic.tools.registry import _registry, _Tool
    count = 0
    for t in tools:
        tool_name = f"mcp_{name}_{t['name']}"
        schema = t.get("inputSchema") or t.get("input_schema") or {
            "type": "object", "properties": {}
        }
        _registry[tool_name] = _Tool(
            name=tool_name,
            description=f"[{name}] {t.get('description', t['name'])}",
            input_schema=schema,
            fn=_make_fn(client, t["name"]),
        )
        count += 1
    return count


def _make_fn(client: StdioMCPClient, tool_name: str):
    def _call(**kwargs) -> str:
        return client.call_tool(tool_name, kwargs)
    _call.__name__ = tool_name
    return _call


def list_server_tools() -> dict[str, list[str]]:
    """Return {server_name: [tool_name, ...]} for all loaded servers."""
    return {
        name: [t["name"] for t in client.list_tools()]
        for name, client in _clients.items()
    }


def get_client(name: str) -> StdioMCPClient | None:
    return _clients.get(name)


def stop_all_servers() -> None:
    for client in _clients.values():
        try:
            client.stop()
        except Exception:
            pass
    _clients.clear()
