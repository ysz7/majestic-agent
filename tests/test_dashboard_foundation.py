"""Tests for dashboard foundation: setup endpoints, config, static serving, auth."""
from __future__ import annotations

import json
import threading
import urllib.request
import urllib.error
from pathlib import Path
import pytest

_PORT = 18766


@pytest.fixture(scope="module", autouse=True)
def _server():
    from majestic.api.server import _Handler
    from http.server import HTTPServer
    srv = HTTPServer(("127.0.0.1", _PORT), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield
    srv.shutdown()


def _get(path: str) -> tuple[int, dict]:
    url = f"http://127.0.0.1:{_PORT}{path}"
    try:
        with urllib.request.urlopen(url) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _post(path: str, body: dict) -> tuple[int, dict]:
    url = f"http://127.0.0.1:{_PORT}{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ── /health ───────────────────────────────────────────────────────────────────

def test_health():
    status, body = _get("/health")
    assert status == 200
    assert body["status"] == "ok"
    assert "version" in body
    assert "uptime" in body


# ── /api/setup/status ─────────────────────────────────────────────────────────

def test_setup_status_returns_configured_field():
    status, body = _get("/api/setup/status")
    assert status == 200
    assert "configured" in body
    assert isinstance(body["configured"], bool)
    assert "has_api_key" in body
    assert "has_model" in body


# ── /api/setup ────────────────────────────────────────────────────────────────

def test_setup_post_requires_body():
    url = f"http://127.0.0.1:{_PORT}/api/setup"
    req = urllib.request.Request(url, data=b"", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            body = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = json.loads(e.read())
    assert "error" in body


def test_setup_post_creates_config(tmp_path, monkeypatch):
    monkeypatch.setenv("MAJESTIC_HOME", str(tmp_path))
    import majestic.constants as mc
    monkeypatch.setattr(mc, "MAJESTIC_HOME", tmp_path)
    monkeypatch.setattr(mc, "CONFIG_FILE", tmp_path / "config.yaml")

    from majestic.api import dashboard as d
    result = d.handle_setup({
        "api_key": "sk-ant-test-key",
        "model": "claude-sonnet-4-6",
        "language": "en",
        "currency": "USD",
    })
    assert result.get("ok") is True
    assert (tmp_path / "config.yaml").exists()
    env_content = (tmp_path / ".env").read_text()
    assert "ANTHROPIC_API_KEY" in env_content


# ── Auth: localhost passes without API key ─────────────────────────────────────

def test_localhost_allowed_without_key():
    # Sessions endpoint should work from localhost without X-API-Key
    status, body = _get("/api/sessions")
    # Either 200 (empty list) or known error, but NOT 401
    assert status != 401


# ── Static serving fallback ───────────────────────────────────────────────────

def test_static_not_found_without_build(tmp_path, monkeypatch):
    import majestic.api.server as srv_mod
    monkeypatch.setattr(srv_mod, "_STATIC", tmp_path / "nonexistent")
    status, body = _get("/some/spa/route")
    # Without static dir, returns 404 JSON
    assert status == 404


def test_static_serves_index_html(tmp_path, monkeypatch):
    import majestic.api.server as srv_mod
    (tmp_path).mkdir(exist_ok=True)
    (tmp_path / "index.html").write_text("<html>test</html>")
    monkeypatch.setattr(srv_mod, "_STATIC", tmp_path)

    url = f"http://127.0.0.1:{_PORT}/any/spa/route"
    with urllib.request.urlopen(url) as r:
        content = r.read().decode()
    assert "test" in content


# ── dashboard.py unit tests ───────────────────────────────────────────────────

def test_handle_get_memory_returns_dict():
    from majestic.api.dashboard import handle_get_memory_md
    result = handle_get_memory_md()
    assert isinstance(result, dict)
    assert "agent" in result
    assert "user" in result


def test_handle_get_skills_returns_list():
    from majestic.api.dashboard import handle_get_skills
    result = handle_get_skills()
    assert isinstance(result, list)


def test_handle_get_tables_returns_list():
    from majestic.api.dashboard import handle_get_tables
    result = handle_get_tables()
    assert isinstance(result, list)


def test_handle_token_stats_shape():
    from majestic.api.dashboard import handle_token_stats
    stats = handle_token_stats()
    assert "total_tokens" in stats
    assert "total_cost_usd" in stats


def test_write_env_helper(tmp_path):
    from majestic.api.dashboard import _write_env
    env_file = tmp_path / ".env"
    _write_env(env_file, {"FOO": "bar", "BAZ": "qux"})
    content = env_file.read_text()
    assert "FOO=bar" in content
    assert "BAZ=qux" in content
    # Overwrite single key
    _write_env(env_file, {"FOO": "new"})
    content2 = env_file.read_text()
    assert "FOO=new" in content2
    assert "BAZ=qux" in content2
