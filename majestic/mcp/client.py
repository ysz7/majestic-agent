"""Real MCP (Model Context Protocol) client — stdio transport.

Replaces the previous stub. Speaks JSON-RPC 2.0 over a server subprocess's
stdin/stdout (newline-delimited), performs the initialize handshake, lists the
server's tools, and calls them. Discovered tools are exposed to the agent's
ReAct loop as async callables named ``mcp__<server>__<tool>`` (Phase K.3).

Registry (majestic/mcp/registry.yaml) entry shape:

    servers:
      git:
        enabled: true                 # only enabled servers are spawned
        runtime: python | node        # used to derive a default command
        package: "mcp-server-git"     # used to derive a default command
        command: ["uvx", "mcp-server-git"]   # optional explicit launch
        args: ["--repo", "."]                 # optional extra args
        env: { KEY: "value" }                 # optional extra env
        description: "git repository operations"

If ``command`` is omitted it is derived from runtime+package:
  python -> [package]            (the installed console script)
  node   -> ["npx", "-y", package]
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Awaitable, Callable

import yaml

logger = logging.getLogger("majestic.mcp")

_PROTOCOL_VERSION = "2024-11-05"
_REQUEST_TIMEOUT = 30.0


def _derive_command(cfg: dict) -> list[str] | None:
    """Build a launch command from an explicit ``command`` or runtime+package."""
    cmd = cfg.get("command")
    if isinstance(cmd, str):
        cmd = [cmd]
    if not cmd:
        runtime = (cfg.get("runtime") or "").lower()
        package = cfg.get("package")
        if not package:
            return None
        if runtime == "node":
            cmd = ["npx", "-y", package]
        else:  # python / default — rely on the installed console script
            cmd = [package]
    return list(cmd) + list(cfg.get("args") or [])


class MCPServer:
    """One MCP server subprocess spoken to over stdio JSON-RPC."""

    def __init__(self, name: str, command: list[str], env: dict | None = None) -> None:
        self.name = name
        self.command = command
        self.env = env or {}
        self.tools: list[dict] = []
        self._proc: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._next_id = 0

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def connect(self) -> None:
        full_env = {**os.environ, **self.env}
        self._proc = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=full_env,
        )
        self._reader_task = asyncio.create_task(self._read_loop())

        await self._request("initialize", {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "majestic", "version": "0.1.0"},
        })
        await self._notify("notifications/initialized", {})

        result = await self._request("tools/list", {})
        self.tools = result.get("tools", []) if isinstance(result, dict) else []
        logger.info("MCP server '%s' ready — %d tools", self.name, len(self.tools))

    async def close(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except (asyncio.TimeoutError, ProcessLookupError):
                try:
                    self._proc.kill()
                except ProcessLookupError:
                    pass

    # ── tool calls ───────────────────────────────────────────────────────────
    async def call_tool(self, tool: str, arguments: dict) -> str:
        result = await self._request("tools/call", {"name": tool, "arguments": arguments})
        return self._flatten_content(result)

    @staticmethod
    def _flatten_content(result: Any) -> str:
        if not isinstance(result, dict):
            return str(result)
        blocks = result.get("content") or []
        parts: list[str] = []
        for b in blocks:
            if isinstance(b, dict):
                if b.get("type") == "text":
                    parts.append(b.get("text", ""))
                else:
                    parts.append(json.dumps(b, ensure_ascii=False))
        text = "\n".join(p for p in parts if p) or json.dumps(result, ensure_ascii=False)
        return f"Error: {text}" if result.get("isError") else text

    # ── JSON-RPC plumbing ──────────────────────────────────────────────────────
    async def _read_loop(self) -> None:
        assert self._proc and self._proc.stdout
        while True:
            line = await self._proc.stdout.readline()
            if not line:
                break  # EOF — server exited
            try:
                msg = json.loads(line.decode("utf-8").strip())
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            mid = msg.get("id")
            if mid is not None and mid in self._pending:
                fut = self._pending.pop(mid)
                if not fut.done():
                    if "error" in msg:
                        fut.set_exception(RuntimeError(str(msg["error"])))
                    else:
                        fut.set_result(msg.get("result", {}))

    async def _send(self, payload: dict) -> None:
        assert self._proc and self._proc.stdin
        self._proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
        await self._proc.stdin.drain()

    async def _request(self, method: str, params: dict) -> dict:
        self._next_id += 1
        mid = self._next_id
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[mid] = fut
        await self._send({"jsonrpc": "2.0", "id": mid, "method": method, "params": params})
        try:
            return await asyncio.wait_for(fut, timeout=_REQUEST_TIMEOUT)
        except asyncio.TimeoutError:
            self._pending.pop(mid, None)
            raise RuntimeError(f"MCP '{self.name}' request '{method}' timed out")

    async def _notify(self, method: str, params: dict) -> None:
        await self._send({"jsonrpc": "2.0", "method": method, "params": params})


class MCPManager:
    """Reads the registry, connects enabled servers, and exposes their tools."""

    def __init__(self, registry_path: str | Path = "majestic/mcp/registry.yaml") -> None:
        self.registry_path = Path(registry_path)
        self._servers: dict[str, MCPServer] = {}

    def _load_registry(self) -> dict:
        if not self.registry_path.exists():
            return {}
        try:
            return yaml.safe_load(self.registry_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}

    async def connect_enabled(self) -> dict[str, Callable[..., Awaitable[str]]]:
        """Spawn every server marked ``enabled: true`` and return a flat dict of
        ``mcp__<server>__<tool>`` async callables for the agent toolset."""
        registry = self._load_registry()
        tools: dict[str, Callable[..., Awaitable[str]]] = {}

        for name, cfg in (registry.get("servers") or {}).items():
            if not isinstance(cfg, dict) or not cfg.get("enabled"):
                continue
            command = _derive_command(cfg)
            if not command:
                logger.warning("MCP server '%s' skipped — no command/package", name)
                continue
            server = MCPServer(name, command, env=cfg.get("env"))
            try:
                await server.connect()
            except Exception as exc:  # noqa: BLE001
                logger.warning("MCP server '%s' failed to start: %s", name, exc)
                await server.close()
                continue
            self._servers[name] = server

            for tool in server.tools:
                tname = tool.get("name")
                if not tname:
                    continue
                full = f"mcp__{name}__{tname}"
                tools[full] = self._make_callable(server, tname, tool)

        return tools

    @staticmethod
    def _make_callable(server: MCPServer, tool: str, schema: dict):
        async def _call(**kwargs) -> str:
            return await server.call_tool(tool, kwargs)
        _call.__name__ = f"mcp_{server.name}_{tool}"
        _call.__doc__ = schema.get("description", f"MCP tool {tool} on {server.name}")
        # Expose the MCP inputSchema so _build_tool_schemas can use it natively.
        _call.mcp_input_schema = schema.get("inputSchema") or {"type": "object", "properties": {}}
        return _call

    async def close_all(self) -> None:
        for server in self._servers.values():
            await server.close()
        self._servers.clear()


# Backwards-compatible thin facade (old name used elsewhere).
class MCPClient(MCPManager):
    pass
