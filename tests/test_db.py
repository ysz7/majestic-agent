"""Tests for StateDB — sessions, messages, FTS5 search, news."""
import pytest


def test_create_and_close_session(db):
    sid = db.create_session(source="test", model="mock")
    assert sid

    rows = db._conn.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchall()
    assert len(rows) == 1
    assert rows[0]["source"] == "test"
    assert rows[0]["model"]  == "mock"

    db.close_session(sid, token_in=10, token_out=5, cost=0.001, message_count=2)
    row = db._conn.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
    assert row["ended_at"] is not None
    assert row["token_count_in"]  == 10
    assert row["token_count_out"] == 5


def test_add_message(db):
    sid = db.create_session(source="test")
    mid = db.add_message(sid, "user", "hello world")
    assert isinstance(mid, int)
    assert mid > 0

    row = db._conn.execute("SELECT * FROM messages WHERE id = ?", (mid,)).fetchone()
    assert row["role"]    == "user"
    assert row["content"] == "hello world"


def test_fts5_search(db):
    sid = db.create_session(source="test")
    db.add_message(sid, "user", "the quick brown fox")
    db.add_message(sid, "assistant", "jumps over the lazy dog")

    results = db.search_messages("fox", k=5)
    assert any("fox" in r["content"] for r in results)

    results2 = db.search_messages("lazy", k=5)
    assert any("lazy" in r["content"] for r in results2)


def test_fts5_no_results(db):
    sid = db.create_session(source="test")
    db.add_message(sid, "user", "hello world")

    results = db.search_messages("xyzzy_notfound", k=5)
    assert results == []


def test_add_and_load_news(db):
    items = [
        {"title": "AI news today", "url": "https://example.com/1", "source": "hn",
         "score": 0.9, "published_at": "2024-01-01T00:00:00"},
        {"title": "Market update", "url": "https://example.com/2", "source": "reddit",
         "score": 0.7, "published_at": "2024-01-02T00:00:00"},
    ]
    count = db.add_news_items(items)
    assert count == 2

    loaded = db.load_news(limit=10)
    assert len(loaded) == 2
    titles = {r["title"] for r in loaded}
    assert "AI news today" in titles
    assert "Market update" in titles


def test_add_multiple_news_batches(db):
    batch1 = [{"title": "Story A", "url": "https://example.com/a", "source": "hn",
               "score": 0.5, "published_at": "2024-01-01T00:00:00"}]
    batch2 = [{"title": "Story B", "url": "https://example.com/b", "source": "hn",
               "score": 0.4, "published_at": "2024-01-02T00:00:00"},
              {"title": "Story C", "url": "https://example.com/c", "source": "hn",
               "score": 0.3, "published_at": "2024-01-03T00:00:00"}]
    db.add_news_items(batch1)
    db.add_news_items(batch2)

    loaded = db.load_news(limit=10)
    assert len(loaded) == 3
    titles = {r["title"] for r in loaded}
    assert titles == {"Story A", "Story B", "Story C"}


def test_search_news_fts(db):
    db.add_news_items([
        {"title": "Bitcoin surges to new high", "url": "https://x.com/1", "source": "hn",
         "score": 0.8, "published_at": "2024-01-01T00:00:00"},
        {"title": "Weather forecast for weekend", "url": "https://x.com/2", "source": "hn",
         "score": 0.3, "published_at": "2024-01-01T00:00:00"},
    ])
    results = db.search_news("Bitcoin", k=5)
    assert any("Bitcoin" in r["title"] for r in results)


def test_add_and_get_chunks(db):
    chunks = [
        {"content": "chunk one text", "embedding": None, "metadata": {"page": 1}},
        {"content": "chunk two text", "embedding": None, "metadata": {"page": 2}},
    ]
    n = db.add_chunks("test_doc.pdf", chunks)
    assert n == 2

    stored = db.get_file_chunks("test_doc.pdf")
    assert len(stored) == 2
    assert "chunk one text" in stored


def test_get_files(db):
    db.add_chunks("alpha.pdf", [{"content": "a", "embedding": None}])
    db.add_chunks("beta.pdf",  [{"content": "b", "embedding": None}])
    files = db.get_files()
    assert "alpha.pdf" in files
    assert "beta.pdf"  in files


def test_delete_file(db):
    db.add_chunks("to_delete.pdf", [{"content": "gone", "embedding": None}])
    deleted = db.delete_file("to_delete.pdf")
    assert deleted >= 1
    assert db.get_file_chunks("to_delete.pdf") == []
