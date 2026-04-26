"""
Minimal mock MCP server for testing — reads JSON-RPC from stdin, writes to stdout.
Run as: python mock_mcp_server.py
"""
import json
import sys


def _send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def _handle(msg: dict) -> None:
    method = msg.get("method", "")
    msg_id = msg.get("id")

    if method == "initialize":
        _send({"jsonrpc": "2.0", "id": msg_id, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "mock-server", "version": "1.0"},
        }})

    elif method == "notifications/initialized":
        pass  # notification, no response

    elif method == "tools/list":
        _send({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": [
            {
                "name": "echo",
                "description": "Echoes the input text",
                "inputSchema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            },
            {
                "name": "add",
                "description": "Adds two numbers",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "number"},
                        "b": {"type": "number"},
                    },
                    "required": ["a", "b"],
                },
            },
        ]}})

    elif method == "tools/call":
        name = msg.get("params", {}).get("name", "")
        args = msg.get("params", {}).get("arguments", {})
        if name == "echo":
            text = args.get("text", "")
            _send({"jsonrpc": "2.0", "id": msg_id, "result": {
                "content": [{"type": "text", "text": f"echo: {text}"}]
            }})
        elif name == "add":
            result = args.get("a", 0) + args.get("b", 0)
            _send({"jsonrpc": "2.0", "id": msg_id, "result": {
                "content": [{"type": "text", "text": str(result)}]
            }})
        else:
            _send({"jsonrpc": "2.0", "id": msg_id, "error": {
                "code": -32601, "message": f"Unknown tool: {name}"
            }})
    else:
        if msg_id is not None:
            _send({"jsonrpc": "2.0", "id": msg_id, "error": {
                "code": -32601, "message": f"Unknown method: {method}"
            }})


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
        _handle(msg)
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
