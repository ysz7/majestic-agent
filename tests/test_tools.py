"""Tests for tool registry — registration, execution, schema generation."""
import pytest
from majestic.tools.registry import _registry, tool, get_schemas, execute


@pytest.fixture(autouse=True)
def isolated_registry():
    """Save and restore registry state around each test."""
    original = dict(_registry)
    yield
    _registry.clear()
    _registry.update(original)


def test_tool_registration():
    @tool("test_greet", "Say hello", {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]})
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    assert "test_greet" in _registry
    assert _registry["test_greet"].description == "Say hello"


def test_execute_registered_tool():
    @tool("test_add", "Add two numbers", {"type": "object", "properties": {}})
    def add(a: int, b: int) -> int:
        return a + b

    result = execute("test_add", {"a": 3, "b": 4})
    assert result == "7"


def test_execute_unknown_tool():
    result = execute("nonexistent_tool_xyz", {})
    assert "[tool error]" in result
    assert "nonexistent_tool_xyz" in result


def test_execute_tool_exception():
    @tool("test_boom", "Always raises", {"type": "object", "properties": {}})
    def boom():
        raise ValueError("kaboom")

    result = execute("test_boom", {})
    assert "[tool error]" in result
    assert "kaboom" in result


def test_execute_none_return():
    @tool("test_noop", "Returns nothing", {"type": "object", "properties": {}})
    def noop():
        return None

    result = execute("test_noop", {})
    assert result == "(no output)"


def test_get_schemas_format():
    @tool("test_schema_tool", "A tool for schema test",
          {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]})
    def schema_tool(x: int) -> str:
        return str(x)

    schemas = get_schemas()
    match = next((s for s in schemas if s["name"] == "test_schema_tool"), None)
    assert match is not None
    assert match["description"]  == "A tool for schema test"
    assert "properties" in match["input_schema"]


def test_tool_overwrite():
    @tool("test_overwrite", "v1", {"type": "object", "properties": {}})
    def v1():
        return "v1"

    @tool("test_overwrite", "v2", {"type": "object", "properties": {}})
    def v2():
        return "v2"

    assert _registry["test_overwrite"].description == "v2"
    assert execute("test_overwrite", {}) == "v2"
