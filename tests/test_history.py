"""Tests for conversation history search and session summarization."""
import pytest


# ── StateDB history methods ───────────────────────────────────────────────────

def test_set_and_get_session_title(db):
    sid = db.create_session(source="test")
    db.set_session_title(sid, "Discussed BTC price trends")
    rows = db.get_recent_sessions(limit=5)
    match = next((r for r in rows if r["id"] == sid), None)
    assert match is not None
    assert match["title"] == "Discussed BTC price trends"


def test_get_session_messages(db):
    sid = db.create_session(source="test")
    db.add_message(sid, "user", "What is the capital of France?")
    db.add_message(sid, "assistant", "The capital of France is Paris.")
    msgs = db.get_session_messages(sid)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"


def test_get_session_messages_empty(db):
    sid = db.create_session(source="test")
    msgs = db.get_session_messages(sid)
    assert msgs == []


def test_search_messages_grouped(db):
    sid = db.create_session(source="test")
    db.add_message(sid, "user", "explain quantum computing basics")
    db.add_message(sid, "assistant", "Quantum computing uses qubits instead of bits")

    results = db.search_messages_grouped("quantum", k=5)
    assert len(results) >= 1
    assert results[0]["session_id"] == sid
    assert len(results[0]["snippets"]) >= 1


def test_search_messages_grouped_no_results(db):
    results = db.search_messages_grouped("xyzzynonexistent", k=5)
    assert results == []


def test_search_messages_grouped_groups_by_session(db):
    sid1 = db.create_session(source="test")
    db.add_message(sid1, "user", "python list comprehension tutorial")
    db.add_message(sid1, "assistant", "Python list comprehensions are concise")

    sid2 = db.create_session(source="test")
    db.add_message(sid2, "user", "python dict comprehension example")
    db.add_message(sid2, "assistant", "Python dict comprehensions work similarly")

    results = db.search_messages_grouped("python", k=5)
    session_ids = {r["session_id"] for r in results}
    assert sid1 in session_ids
    assert sid2 in session_ids


def test_recent_sessions_includes_title(db):
    sid = db.create_session(source="test")
    db.set_session_title(sid, "Test session summary")
    rows = db.get_recent_sessions(limit=10)
    match = next((r for r in rows if r["id"] == sid), None)
    assert match["title"] == "Test session summary"


# ── history_search tool ───────────────────────────────────────────────────────

def test_history_search_no_results(db):
    from majestic.tools.history_search import history_search
    result = history_search("xyzzy_nonexistent_topic_12345")
    assert "No matching" in result


def test_history_search_returns_string(db):
    sid = db.create_session(source="test")
    db.add_message(sid, "user", "renewable energy solar panels")
    db.add_message(sid, "assistant", "Solar panels convert sunlight to electricity")

    from majestic.tools.history_search import history_search
    result = history_search("solar")
    assert isinstance(result, str)
    assert len(result) > 0


# ── session_summarizer ────────────────────────────────────────────────────────

def test_summarize_session_no_messages(db):
    sid = db.create_session(source="test")
    from majestic.memory.session_summarizer import _run
    _run(sid)  # should not raise, title stays None
    rows = db.get_recent_sessions(limit=5)
    match = next((r for r in rows if r["id"] == sid), None)
    assert match["title"] is None
