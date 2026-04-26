"""
Stdio MCP client — communicates with an MCP server subprocess via newline-delimited JSON-RPC 2.0.

Protocol:
  1. spawn subprocess with given command
  2. send initialize request, receive response
  3. send notifications/initialized
  4. ready to call tools/list and tools/call
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
from typing import Any


class StdioMCPClient:
    TIMEOUT = 15.0

    def __init__(self, name: str, command: list[str], env: dict[str, str] | None = None):
        self.name     = name
        self._command = command
        self._env     = env or {}
        self._proc:   subprocess.Popen | None = None
        self._lock    = threading.Lock()
        self._id      = 0
        self._tools:  list[dict] | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        merged_env = {**os.environ, **{
            k: _expand_env(v) for k, v in self._env.items()
        }}
        self._proc = subprocess.Popen(
            self._command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=merged_env,
        )
        self._initialize()

    def stop(self) -> None:
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # ── Public API ────────────────────────────────────────────────────────────

    def list_tools(self) -> list[dict]:
        if self._tools is not None:
            return self._tools
        result = self._request("tools/list", {})
        self._tools = result.get("tools", [])
        return self._tools

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        result = self._request("tools/call", {"name": tool_name, "arguments": arguments})
        content = result.get("content", [])
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "error":
                    parts.append(f"[error] {block.get('text', '')}")
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts) if parts else str(result)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _initialize(self) -> None:
        self._request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities":    {},
            "clientInfo":      {"name": "majestic", "version": "1.0"},
        })
        self._notify("notifications/initialized", {})

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _send(self, obj: dict) -> None:
        assert self._proc and self._proc.stdin
        line = json.dumps(obj, ensure_ascii=False) + "\n"
        self._proc.stdin.write(line.encode())
        self._proc.stdin.flush()

    def _recv(self) -> dict:
        assert self._proc and self._proc.stdout
        line = self._proc.stdout.readline()
        if not line:
            raise RuntimeError(f"MCP server '{self.name}' closed stdout")
        return json.loads(line.decode().strip())

    def _notify(self, method: str, params: dict) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _request(self, method: str, params: dict) -> Any:
        with self._lock:
            req_id = self._next_id()
            self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
            while True:
                msg = self._recv()
                if msg.get("id") == req_id:
                    if "error" in msg:
                        raise RuntimeError(f"MCP error: {msg['error']}")
                    return msg.get("result", {})


def _expand_env(value: str) -> str:
    """Expand ${VAR} references in env values."""
    import re
    return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), value)
