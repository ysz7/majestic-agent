"""Tests for dashboard settings, memory and skills endpoints."""
from __future__ import annotations

import json
import threading
import urllib.request
import urllib.error
import pytest

_PORT = 18768


@pytest.fixture(scope="module", autouse=True)
def _server():
    from majestic.api.server import _Handler
    from http.server import HTTPServer
    srv = HTTPServer(("127.0.0.1", _PORT), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield
    srv.shutdown()


def _get(path: str) -> tuple[int, object]:
    url = f"http://127.0.0.1:{_PORT}{path}"
    try:
        with urllib.request.urlopen(url) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _post(path: str, body: dict) -> tuple[int, object]:
    url = f"http://127.0.0.1:{_PORT}{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _delete(path: str) -> tuple[int, object]:
    url = f"http://127.0.0.1:{_PORT}{path}"
    req = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ── Settings ──────────────────────────────────────────────────────────────────

def test_get_settings_returns_dict():
    status, body = _get("/api/settings")
    assert status == 200
    assert isinstance(body, dict)


def test_get_settings_has_llm_section():
    _, body = _get("/api/settings")
    assert "llm" in body or "language" in body


def test_get_settings_no_raw_api_key():
    _, body = _get("/api/settings")
    assert isinstance(body, dict)
    llm = body.get("llm", {})
    assert "api_key" not in llm, "Raw API key should not be exposed"


def test_get_settings_has_key_preview():
    _, body = _get("/api/settings")
    assert isinstance(body, dict)
    assert "_api_key_set" in body
    assert isinstance(body["_api_key_set"], bool)


def test_handle_get_settings_unit():
    from majestic.api.dashboard import handle_get_settings
    result = handle_get_settings()
    assert isinstance(result, dict)
    assert "llm" in result or "language" in result
    # No raw key
    llm = result.get("llm", {})
    assert "api_key" not in llm


# ── Settings save ─────────────────────────────────────────────────────────────

def test_handle_save_settings_unit(tmp_path, monkeypatch):
    import majestic.constants as mc
    monkeypatch.setattr(mc, "MAJESTIC_HOME", tmp_path)
    monkeypatch.setattr(mc, "CONFIG_FILE", tmp_path / "config.yaml")

    from majestic.api.dashboard import handle_save_settings
    result = handle_save_settings({
        "language": "uk",
        "currency": "UAH",
        "llm": {"model": "claude-sonnet-4-6", "provider": "anthropic"},
    })
    assert result.get("ok") is True
    assert (tmp_path / "config.yaml").exists()
    content = (tmp_path / "config.yaml").read_text()
    assert "uk" in content


# ── Memory ────────────────────────────────────────────────────────────────────

def test_get_memory_returns_agent_and_user():
    status, body = _get("/api/memory")
    assert status == 200
    assert isinstance(body, dict)
    assert "agent" in body
    assert "user" in body


def test_handle_get_memory_unit():
    from majestic.api.dashboard import handle_get_memory_md
    result = handle_get_memory_md()
    assert isinstance(result, dict)
    assert "agent" in result
    assert "user" in result
    assert isinstance(result["agent"], str)
    assert isinstance(result["user"], str)


def test_handle_save_memory_unit(tmp_path, monkeypatch):
    import majestic.constants as mc
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir()
    monkeypatch.setattr(mc, "MEMORY_DIR", mem_dir)

    import majestic.memory.store as ms
    monkeypatch.setattr(ms, "MEMORY_FILE", mem_dir / "memory.md")
    monkeypatch.setattr(ms, "USER_FILE", mem_dir / "user.md")

    from majestic.api.dashboard import handle_save_memory_md
    result = handle_save_memory_md({"agent": "test agent memory", "user": "test user profile"})
    assert result.get("ok") is True
    assert "test agent memory" in (mem_dir / "memory.md").read_text()
    assert "test user profile" in (mem_dir / "user.md").read_text()


# ── Skills ────────────────────────────────────────────────────────────────────

def test_get_skills_returns_list():
    status, body = _get("/api/skills")
    assert status == 200
    assert isinstance(body, list)


def test_skills_have_required_fields():
    _, body = _get("/api/skills")
    for skill in body:
        assert "name" in skill
        assert "description" in skill
        assert "builtin" in skill


def test_create_and_delete_skill(tmp_path, monkeypatch):
    import majestic.constants as mc
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setattr(mc, "SKILLS_DIR", skills_dir)

    from majestic.api.dashboard import handle_create_skill, handle_get_skills, handle_delete_skill

    result = handle_create_skill({
        "name": "test-skill",
        "description": "A test skill",
        "body": "## Goal\nTest the skill system.",
        "tags": ["test"],
    })
    assert result.get("ok") is True

    skills = handle_get_skills()
    names = [s["name"] for s in skills]
    assert "test-skill" in names

    del_result = handle_delete_skill("test-skill")
    assert del_result.get("ok") is True

    skills_after = handle_get_skills()
    names_after = [s["name"] for s in skills_after]
    assert "test-skill" not in names_after


def test_get_skill_detail_unit(tmp_path, monkeypatch):
    import majestic.constants as mc
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setattr(mc, "SKILLS_DIR", skills_dir)

    from majestic.api.dashboard import handle_create_skill, handle_get_skill_detail

    handle_create_skill({
        "name": "detail-skill",
        "description": "Detail test",
        "body": "## Goal\ndetail body",
        "tags": [],
    })
    detail = handle_get_skill_detail("detail-skill")
    assert "body" in detail
    assert "detail body" in detail["body"]


def test_builtin_skills_appear():
    from majestic.api.dashboard import handle_get_skills
    skills = handle_get_skills()
    # Builtins come from the built-in directory — just verify the list works
    assert isinstance(skills, list)
