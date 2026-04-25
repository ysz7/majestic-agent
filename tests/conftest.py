"""Shared fixtures for all tests."""
import pytest


@pytest.fixture
def tmp_home(tmp_path, monkeypatch):
    """Point MAJESTIC_HOME at a temp dir so tests never touch ~/.majestic-agent."""
    monkeypatch.setenv("MAJESTIC_HOME", str(tmp_path))

    # Patch module-level constants
    import majestic.constants as _c
    _c.MAJESTIC_HOME = tmp_path
    _c.STATE_DB      = tmp_path / "state.db"
    _c.MEMORY_DIR    = tmp_path / "memory"
    _c.SKILLS_DIR    = tmp_path / "skills"
    _c.EXPORTS_DIR   = tmp_path / "exports"
    _c.WORKSPACE_DIR = tmp_path / "workspace"

    # Patch cached imports in sub-modules
    import majestic.db.state as _ds
    monkeypatch.setattr(_ds, "STATE_DB", tmp_path / "state.db")

    import majestic.memory.store as _ms
    mem_dir = tmp_path / "memory"
    monkeypatch.setattr(_ms, "MEMORY_DIR",  mem_dir)
    monkeypatch.setattr(_ms, "MEMORY_FILE", mem_dir / "memory.md")
    monkeypatch.setattr(_ms, "USER_FILE",   mem_dir / "user.md")

    return tmp_path


@pytest.fixture
def db(tmp_home):
    """Fresh StateDB backed by a temp file."""
    from majestic.db.state import StateDB
    instance = StateDB(db_path=tmp_home / "state.db")
    yield instance
    instance.close()
