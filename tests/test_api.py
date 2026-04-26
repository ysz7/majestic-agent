"""Tests for REST API server."""
import json
import threading
import urllib.request
import urllib.error
import pytest

_PORT = 18765  # isolated port for tests


@pytest.fixture(scope="module", autouse=True)
def _api_server():
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


def _post(path: str, data: dict, key: str = "") -> tuple[int, dict]:
    url = f"http://127.0.0.1:{_PORT}{path}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Content-Length", str(len(body)))
    if key:
        req.add_header("X-API-Key", key)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_health():
    status, body = _get("/health")
    assert status == 200
    assert body["status"] == "ok"
    assert "version" in body


def test_unknown_route():
    status, body = _get("/nonexistent")
    assert status == 404


def test_chat_missing_message():
    status, body = _post("/chat", {})
    assert status == 400
    assert "message" in body["error"]


def test_chat_empty_body():
    url = f"http://127.0.0.1:{_PORT}/chat"
    req = urllib.request.Request(url, data=b"", method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Content-Length", "0")
    try:
        with urllib.request.urlopen(req) as r:
            status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
    assert status == 400


def test_run_missing_prompt():
    status, body = _post("/run", {})
    assert status == 400
    assert "prompt" in body["error"]


def test_run_accepted():
    status, body = _post("/run", {"prompt": "hello"})
    assert status == 202
    assert body["status"] == "accepted"


def test_auth_required(monkeypatch):
    import majestic.api.server as srv
    monkeypatch.setattr(srv, "_api_key", lambda: "secret123")
    status, body = _get("/sessions")
    assert status == 401
    monkeypatch.undo()


def test_auth_valid(monkeypatch):
    import majestic.api.server as srv
    monkeypatch.setattr(srv, "_api_key", lambda: "secret123")
    url = f"http://127.0.0.1:{_PORT}/sessions"
    req = urllib.request.Request(url)
    req.add_header("X-API-Key", "secret123")
    with urllib.request.urlopen(req) as r:
        assert r.status == 200
    monkeypatch.undo()
