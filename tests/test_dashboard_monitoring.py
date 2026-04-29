"""Tests for the dashboard monitoring endpoint."""
from __future__ import annotations

import json
import threading
import urllib.request
import urllib.error
import pytest

_PORT = 18769


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


def _delete(path: str) -> tuple[int, object]:
    url = f"http://127.0.0.1:{_PORT}{path}"
    req = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ── GET /api/monitoring ───────────────────────────────────────────────────────

def test_monitoring_returns_200():
    status, _ = _get("/api/monitoring")
    assert status == 200


def test_monitoring_has_tokens_section():
    _, body = _get("/api/monitoring")
    assert isinstance(body, dict)
    assert "tokens" in body


def test_monitoring_tokens_has_required_fields():
    _, body = _get("/api/monitoring")
    tokens = body["tokens"]
    for field in ("total_in", "total_out", "total_cost_usd", "requests", "by_day"):
        assert field in tokens, f"Missing field: {field}"


def test_monitoring_by_day_is_list():
    _, body = _get("/api/monitoring")
    assert isinstance(body["tokens"]["by_day"], list)


def test_monitoring_has_schedules():
    _, body = _get("/api/monitoring")
    assert "schedules" in body
    assert isinstance(body["schedules"], list)


def test_monitoring_has_reminders():
    _, body = _get("/api/monitoring")
    assert "reminders" in body
    assert isinstance(body["reminders"], list)


# ── handle_get_monitoring unit ────────────────────────────────────────────────

def test_handle_get_monitoring_unit():
    from majestic.api.dashboard import handle_get_monitoring
    result = handle_get_monitoring()
    assert isinstance(result, dict)
    assert "tokens" in result
    assert "schedules" in result
    assert "reminders" in result


def test_handle_get_monitoring_token_types():
    from majestic.api.dashboard import handle_get_monitoring
    tokens = handle_get_monitoring()["tokens"]
    assert isinstance(tokens["total_in"], (int, float))
    assert isinstance(tokens["total_out"], (int, float))
    assert isinstance(tokens["total_cost_usd"], (int, float))
    assert isinstance(tokens["requests"], (int, float))
    assert isinstance(tokens["by_day"], list)


def test_handle_get_monitoring_day_entry_shape(monkeypatch):
    """Inject a fake history entry and verify by_day aggregation."""
    import majestic.token_tracker as tt
    fake_stats = {
        "tokens_in": 100,
        "tokens_out": 50,
        "cost_usd": 0.001,
        "requests": 1,
        "history": [
            {"ts": "2026-04-29T10:00:00", "in": 100, "out": 50, "cost": 0.001},
        ],
    }
    monkeypatch.setattr(tt, "get_stats", lambda: fake_stats)

    from majestic.api.dashboard import handle_get_monitoring
    result = handle_get_monitoring()
    by_day = result["tokens"]["by_day"]
    assert len(by_day) == 1
    day = by_day[0]
    assert day["date"] == "2026-04-29"
    assert day["tokens_in"] == 100
    assert day["tokens_out"] == 50
    assert day["requests"] == 1
    assert abs(day["cost"] - 0.001) < 1e-9


def test_handle_get_monitoring_multiple_days(monkeypatch):
    import majestic.token_tracker as tt
    fake_stats = {
        "tokens_in": 300,
        "tokens_out": 150,
        "cost_usd": 0.003,
        "requests": 3,
        "history": [
            {"ts": "2026-04-28T08:00:00", "in": 50, "out": 25, "cost": 0.0005},
            {"ts": "2026-04-28T15:00:00", "in": 80, "out": 40, "cost": 0.0008},
            {"ts": "2026-04-29T10:00:00", "in": 170, "out": 85, "cost": 0.0017},
        ],
    }
    monkeypatch.setattr(tt, "get_stats", lambda: fake_stats)

    from majestic.api.dashboard import handle_get_monitoring
    by_day = handle_get_monitoring()["tokens"]["by_day"]
    dates = {d["date"] for d in by_day}
    assert "2026-04-28" in dates
    assert "2026-04-29" in dates

    apr28 = next(d for d in by_day if d["date"] == "2026-04-28")
    assert apr28["requests"] == 2
    assert apr28["tokens_in"] == 130


# ── DELETE /api/schedules/:id ─────────────────────────────────────────────────

def test_delete_schedule_nonexistent_returns_ok_or_error():
    status, body = _delete("/api/schedules/99999")
    assert status in (200, 404)
    assert isinstance(body, dict)
