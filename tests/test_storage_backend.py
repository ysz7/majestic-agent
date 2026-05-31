"""Phase 11 — pluggable storage backend contract + SQLite implementation."""
import os
import shutil
import pytest
from pathlib import Path


def _make_profile(tmp_root: str, name: str = "_tmp_backend_test") -> str:
    """Create a throwaway profile and return its name."""
    from majestic.cli.setup import _init_profile
    _init_profile(name, agent_name="Tmp")
    return name


def test_sqlite_backend_implements_contract_and_returns_stores():
    from majestic.config.settings import Settings
    from majestic.storage import get_backend, StorageBackend

    name = "_tmp_backend_test"
    pdir = Path("profiles") / name
    try:
        from majestic.cli.setup import _init_profile
        _init_profile(name, agent_name="Tmp")

        s = Settings(name)
        assert s.db_backend == "sqlite"

        backend = get_backend(s)
        assert isinstance(backend, StorageBackend)

        # every contract method returns a usable store
        for getter in ("pains", "research", "episodic", "semantic",
                       "lessons", "user_profile", "script_tracker", "checkpoints"):
            store = getattr(backend, getter)()
            assert store is not None
            if hasattr(store, "close"):
                store.close()

        wm = backend.working(session_id="t")
        assert wm is not None
    finally:
        import gc
        gc.collect()  # release lingering sqlite handles before Windows rmtree
        if pdir.exists():
            shutil.rmtree(pdir, ignore_errors=True)


def test_unknown_backend_raises():
    from majestic.config.settings import Settings
    from majestic.storage import get_backend

    name = "_tmp_backend_test2"
    pdir = Path("profiles") / name
    try:
        from majestic.cli.setup import _init_profile
        _init_profile(name, agent_name="Tmp")

        os.environ["MAJESTIC_DB_BACKEND"] = "postgres"
        s = Settings(name)
        assert s.db_backend == "postgres"
        with pytest.raises(NotImplementedError):
            get_backend(s)
    finally:
        os.environ.pop("MAJESTIC_DB_BACKEND", None)
        import gc
        gc.collect()  # release lingering sqlite handles before Windows rmtree
        if pdir.exists():
            shutil.rmtree(pdir, ignore_errors=True)


if __name__ == "__main__":
    test_sqlite_backend_implements_contract_and_returns_stores()
    test_unknown_backend_raises()
    print("All storage backend tests passed!")
