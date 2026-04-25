"""Tests for cron jobs — CRUD, scheduler tick, nl_to_schedule mock."""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def use_tmp_db(tmp_home):
    pass


def test_add_and_list_schedule():
    from majestic.cron.jobs import add_schedule, list_schedules

    row = add_schedule(
        name="test-daily",
        cron_expr="0 9 * * *",
        prompt="run briefing",
        delivery_target="cli",
    )
    assert row["name"]      == "test-daily"
    assert row["cron_expr"] == "0 9 * * *"
    assert row["enabled"]   == 1

    schedules = list_schedules()
    assert any(s["name"] == "test-daily" for s in schedules)


def test_remove_schedule():
    from majestic.cron.jobs import add_schedule, remove_schedule, list_schedules

    row = add_schedule("to-remove", "0 10 * * *", "do something")
    removed = remove_schedule(row["id"])
    assert removed is True

    schedules = list_schedules()
    assert not any(s["name"] == "to-remove" for s in schedules)


def test_remove_nonexistent():
    from majestic.cron.jobs import remove_schedule
    result = remove_schedule(99999)
    assert result is False


def test_set_enabled():
    from majestic.cron.jobs import add_schedule, set_enabled, list_schedules

    row = add_schedule("toggle-test", "0 8 * * *", "test")
    set_enabled(row["id"], False)

    schedules = list_schedules()
    match = next(s for s in schedules if s["name"] == "toggle-test")
    assert match["enabled"] == 0

    set_enabled(row["id"], True)
    schedules = list_schedules()
    match = next(s for s in schedules if s["name"] == "toggle-test")
    assert match["enabled"] == 1


def test_enabled_only_filter():
    from majestic.cron.jobs import add_schedule, set_enabled, list_schedules

    row1 = add_schedule("enabled-sched",  "0 1 * * *", "task1")
    row2 = add_schedule("disabled-sched", "0 2 * * *", "task2")
    set_enabled(row2["id"], False)

    active = list_schedules(enabled_only=True)
    names = {s["name"] for s in active}
    assert "enabled-sched"  in names
    assert "disabled-sched" not in names


def test_get_due():
    from majestic.cron.jobs import add_schedule, get_due
    from majestic.db.state import StateDB

    row = add_schedule("overdue", "0 0 * * *", "past task")

    # Force next_run to be in the past
    past = (datetime.now() - timedelta(days=1)).isoformat()
    db = StateDB()
    db._conn.execute("UPDATE schedules SET next_run = ? WHERE id = ?", (past, row["id"]))
    db._conn.commit()

    due = get_due(now=datetime.now())
    assert any(s["name"] == "overdue" for s in due)


def test_get_due_future_not_returned():
    from majestic.cron.jobs import add_schedule, get_due

    add_schedule("future", "0 0 1 1 *", "not yet")  # Jan 1 midnight
    due = get_due(now=datetime(2020, 1, 1, 0, 0, 0))  # far past — only items before this
    # The schedule's next_run was computed from datetime.now() (future), so it's not due in 2020
    assert not any(s["name"] == "future" for s in due)


def test_mark_ran_sets_last_run():
    from majestic.cron.jobs import add_schedule, mark_ran
    from majestic.db.state import StateDB

    row = add_schedule("mark-test", "0 9 * * *", "task")
    assert row["last_run"] is None

    mark_ran(row["id"])

    db = StateDB()
    updated = db._conn.execute(
        "SELECT * FROM schedules WHERE id = ?", (row["id"],)
    ).fetchone()
    assert updated["last_run"] is not None


def test_mark_ran_advances_next_run():
    from majestic.cron.jobs import add_schedule, mark_ran
    from majestic.db.state import StateDB

    row = add_schedule("advance-test", "0 9 * * *", "task")

    # Set next_run to 24h ago so it's clearly in the past
    past = (datetime.now() - timedelta(days=1)).isoformat()
    db = StateDB()
    db._conn.execute("UPDATE schedules SET next_run = ? WHERE id = ?", (past, row["id"]))
    db._conn.commit()

    mark_ran(row["id"])

    updated = db._conn.execute(
        "SELECT next_run FROM schedules WHERE id = ?", (row["id"],)
    ).fetchone()
    # After mark_ran, next_run should be >= now (advanced from the past value)
    assert updated["next_run"] > past


def test_nl_to_schedule_mock():
    from majestic.cron.jobs import nl_to_schedule
    from majestic.llm.base import LLMResponse, Usage

    mock_json = '{"name":"daily-briefing","cron":"0 9 * * *","prompt":"generate briefing","target":"cli"}'

    with patch("majestic.llm.get_provider") as mock_get:
        mock_provider = mock_get.return_value
        mock_provider.complete.return_value = LLMResponse(content=mock_json, usage=Usage())
        result = nl_to_schedule("every day at 9am do a briefing")

    assert result["name"]   == "daily-briefing"
    assert result["cron"]   == "0 9 * * *"
    assert result["prompt"] == "generate briefing"
    assert result["target"] == "cli"


def test_nl_to_schedule_code_fence():
    from majestic.cron.jobs import nl_to_schedule
    from majestic.llm.base import LLMResponse, Usage

    fenced = '```json\n{"name":"x","cron":"0 1 * * *","prompt":"task","target":"cli"}\n```'

    with patch("majestic.llm.get_provider") as mock_get:
        mock_provider = mock_get.return_value
        mock_provider.complete.return_value = LLMResponse(content=fenced, usage=Usage())
        result = nl_to_schedule("every night at 1am do task")

    assert result["name"] == "x"
