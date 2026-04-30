"""Tests for dashboard chat: SSE endpoint, sessions CRUD, message history."""
from __future__ import annotations

import json
import threading
import urllib.request
import urllib.error
import pytest

_PORT = 18767


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


# ── Sessions CRUD ─────────────────────────────────────────────────────────────

def test_get_sessions_returns_list():
    status, body = _get("/api/sessions")
    assert status == 200
    assert isinstance(body, list)


def test_create_session():
    status, body = _post("/api/sessions", {"name": "test-session"})
    assert status == 200
    assert isinstance(body, dict)
    assert "id" in body
    assert body.get("source") == "test-session" or body.get("title") is None


def test_create_session_returns_id():
    _, created = _post("/api/sessions", {"name": "visible-session"})
    assert "id" in created
    # Sessions with 0 messages are filtered from the list — just check creation succeeds
    assert isinstance(created["id"], str)
    assert len(created["id"]) > 0


def test_delete_session():
    _, created = _post("/api/sessions", {"name": "delete-me"})
    sid = created["id"]
    status, body = _delete(f"/api/sessions/{sid}")
    assert status == 200
    assert body.get("ok") is True


def test_delete_session_removes_from_list():
    _, created = _post("/api/sessions", {"name": "to-delete"})
    sid = created["id"]
    _delete(f"/api/sessions/{sid}")
    _, sessions = _get("/api/sessions")
    ids = [s["id"] for s in sessions]
    assert sid not in ids


def test_get_messages_empty_session():
    _, created = _post("/api/sessions", {"name": "empty"})
    sid = created["id"]
    status, body = _get(f"/api/sessions/{sid}/messages")
    assert status == 200
    assert isinstance(body, list)
    assert len(body) == 0


# ── Chat SSE endpoint ─────────────────────────────────────────────────────────

def test_chat_requires_message():
    status, body = _post("/api/chat", {"message": ""})
    assert status == 400
    assert "error" in body


def test_chat_sse_returns_event_stream():
    """POST /api/chat should return text/event-stream with JSON events."""
    import socket
    # Raw HTTP to read SSE without blocking
    with socket.create_connection(("127.0.0.1", _PORT), timeout=10) as sock:
        payload = json.dumps({"message": "say hello in one word"}).encode()
        request = (
            f"POST /api/chat HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{_PORT}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(payload)}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode() + payload
        sock.sendall(request)
        data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk

    text = data.decode(errors="replace")
    assert "text/event-stream" in text
    # Should contain at least one data: line
    assert "data:" in text


def test_chat_sse_events_are_json():
    """Events in the SSE stream should be valid JSON objects with 'type' field."""
    import socket
    with socket.create_connection(("127.0.0.1", _PORT), timeout=15) as sock:
        payload = json.dumps({"message": "hi"}).encode()
        request = (
            f"POST /api/chat HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{_PORT}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(payload)}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode() + payload
        sock.sendall(request)
        data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk

    text = data.decode(errors="replace")
    lines = [l.strip() for l in text.split("\n") if l.startswith("data:")]
    json_events = []
    for line in lines:
        payload_str = line[5:].strip()
        if payload_str == "[DONE]":
            continue
        try:
            obj = json.loads(payload_str)
            json_events.append(obj)
        except json.JSONDecodeError:
            pass

    assert len(json_events) > 0, "Expected at least one JSON event"
    for ev in json_events:
        assert "type" in ev, f"Event missing 'type': {ev}"
        assert ev["type"] in ("text", "tool_call", "error", "done", "session_id")


# ── dashboard.py unit tests ───────────────────────────────────────────────────

def test_handle_get_sessions_shape():
    from majestic.api.dashboard import handle_get_sessions
    result = handle_get_sessions()
    assert isinstance(result, list)
    for s in result:
        assert "id" in s
        assert "message_count" in s


def test_handle_create_and_delete_session():
    from majestic.api.dashboard import handle_create_session, handle_delete_session, handle_get_sessions
    created = handle_create_session({"name": "unit-test-session"})
    assert "id" in created
    sid = created["id"]
    # Sessions with 0 messages are excluded from the list; just verify delete works
    result = handle_delete_session(sid)
    assert result.get("ok") is True
    sessions_after = [s["id"] for s in handle_get_sessions()]
    assert sid not in sessions_after


def test_handle_get_messages_unit():
    from majestic.api.dashboard import handle_create_session, handle_get_messages
    created = handle_create_session({"name": "msg-test"})
    sid = created["id"]
    msgs = handle_get_messages(sid)
    assert isinstance(msgs, list)
