"""Tests for MCP client and bridge."""
import sys
from pathlib import Path
import pytest

_MOCK_SERVER = str(Path(__file__).parent / "mock_mcp_server.py")
_CMD = [sys.executable, _MOCK_SERVER]


# ── StdioMCPClient ────────────────────────────────────────────────────────────

@pytest.fixture
def mcp_client():
    from majestic.mcp.client import StdioMCPClient
    client = StdioMCPClient(name="mock", command=_CMD)
    client.start()
    yield client
    client.stop()


def test_client_starts_and_is_alive(mcp_client):
    assert mcp_client.is_alive()


def test_client_list_tools(mcp_client):
    tools = mcp_client.list_tools()
    assert isinstance(tools, list)
    assert len(tools) == 2
    names = [t["name"] for t in tools]
    assert "echo" in names
    assert "add" in names


def test_client_list_tools_cached(mcp_client):
    tools1 = mcp_client.list_tools()
    tools2 = mcp_client.list_tools()
    assert tools1 is tools2  # same object — cached


def test_client_call_echo(mcp_client):
    result = mcp_client.call_tool("echo", {"text": "hello world"})
    assert "hello world" in result


def test_client_call_add(mcp_client):
    result = mcp_client.call_tool("add", {"a": 3, "b": 4})
    assert "7" in result


def test_client_stop(mcp_client):
    mcp_client.stop()
    assert not mcp_client.is_alive()


# ── bridge — env expansion ────────────────────────────────────────────────────

def test_expand_env_variable(monkeypatch):
    monkeypatch.setenv("MY_TEST_VAR", "hello")
    from majestic.mcp.client import _expand_env
    assert _expand_env("${MY_TEST_VAR}/path") == "hello/path"


def test_expand_env_missing_variable():
    from majestic.mcp.client import _expand_env
    assert _expand_env("${NONEXISTENT_XYZ_VAR}") == ""


def test_expand_env_no_vars():
    from majestic.mcp.client import _expand_env
    assert _expand_env("plain text") == "plain text"


# ── bridge — load_all_servers ─────────────────────────────────────────────────

def test_load_all_servers_empty_config(monkeypatch):
    import majestic.mcp.bridge as bridge
    monkeypatch.setattr("majestic.config.get", lambda key, default=None: [] if key == "mcp_servers" else default)
    old_clients = dict(bridge._clients)
    count = bridge.load_all_servers()
    assert count == 0
    bridge._clients.update(old_clients)


def test_load_server_registers_tools(monkeypatch):
    import majestic.mcp.bridge as bridge
    import majestic.tools.registry as reg

    before = set(reg._registry.keys())
    count = bridge._load_server("testmock", _CMD, {})
    after = set(reg._registry.keys())
    new_tools = after - before

    assert count == 2
    assert "mcp_testmock_echo" in new_tools
    assert "mcp_testmock_add" in new_tools

    # cleanup
    for t in new_tools:
        reg._registry.pop(t, None)
    bridge._clients.pop("testmock", None).stop()


def test_list_server_tools_after_load(monkeypatch):
    import majestic.mcp.bridge as bridge
    import majestic.tools.registry as reg

    bridge._load_server("listtest", _CMD, {})
    result = bridge.list_server_tools()
    assert "listtest" in result
    assert "echo" in result["listtest"]

    # cleanup
    for k in list(reg._registry.keys()):
        if k.startswith("mcp_listtest_"):
            reg._registry.pop(k)
    bridge._clients.pop("listtest", None).stop()


def test_stop_all_servers():
    import majestic.mcp.bridge as bridge
    import majestic.tools.registry as reg

    bridge._load_server("stoptest", _CMD, {})
    assert "stoptest" in bridge._clients
    bridge.stop_all_servers()
    assert "stoptest" not in bridge._clients

    for k in list(reg._registry.keys()):
        if k.startswith("mcp_stoptest_"):
            reg._registry.pop(k)
