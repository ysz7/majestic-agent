"""Tests for persistent memory store — load, append, forget."""
import pytest


@pytest.fixture(autouse=True)
def isolated_memory(tmp_home):
    """Force memory module to use tmp_home paths (conftest already patches these)."""
    yield


def test_load_empty_memory():
    from majestic.memory.store import load_memory, load_user
    assert load_memory() == ""
    assert load_user()   == ""


def test_load_both_empty():
    from majestic.memory.store import load_both
    assert load_both() == ""


def test_append_memory():
    from majestic.memory.store import append_memory, load_memory
    append_memory("User prefers dark mode.")
    content = load_memory()
    assert "User prefers dark mode." in content


def test_append_user():
    from majestic.memory.store import append_user, load_user
    append_user("Name: Alice, role: developer.")
    content = load_user()
    assert "Alice" in content


def test_append_dedup():
    from majestic.memory.store import append_memory, load_memory
    append_memory("Unique fact.")
    append_memory("Unique fact.")
    content = load_memory()
    assert content.count("Unique fact.") == 1


def test_load_both_combined():
    from majestic.memory.store import append_memory, append_user, load_both
    append_user("User info here.")
    append_memory("Agent knows this.")
    combined = load_both()
    assert "User info here." in combined
    assert "Agent knows this." in combined


def test_forget_removes_entry():
    from majestic.memory.store import append_memory, forget, load_memory
    append_memory("Project X deadline is Friday.")
    assert "Project X" in load_memory()
    removed = forget("Project X")
    assert removed >= 1
    assert "Project X" not in load_memory()


def test_forget_no_match():
    from majestic.memory.store import append_memory, forget
    append_memory("Something unrelated.")
    removed = forget("nonexistent_keyword_xyz")
    assert removed == 0


def test_forget_in_user_file():
    from majestic.memory.store import append_user, forget, load_user
    append_user("User loves Python.")
    assert "Python" in load_user()
    removed = forget("Python")
    assert removed >= 1
    assert "Python" not in load_user()


def test_show_returns_string():
    from majestic.memory.store import show
    result = show()
    assert isinstance(result, str)
    assert "User Profile" in result
    assert "Agent Memory" in result
