"""Tests for dashboard tables CRUD and user-table schema injection."""
from __future__ import annotations

import sqlite3
import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Provide a fresh SQLite DB and patch DB_PATH to point to it."""
    db_file = tmp_path / "state.db"
    import majestic.constants as mc
    monkeypatch.setattr(mc, "DB_PATH", db_file)
    return db_file


# ── handle_get_tables ─────────────────────────────────────────────────────────

def test_get_tables_empty(tmp_db):
    from majestic.api.dashboard import handle_get_tables
    result = handle_get_tables()
    assert result == []


def test_get_tables_lists_user_tables(tmp_db):
    con = sqlite3.connect(tmp_db)
    con.execute('CREATE TABLE "user_notes" (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, body TEXT)')
    con.execute("INSERT INTO user_notes (title, body) VALUES ('t1', 'b1')")
    con.commit()
    con.close()

    from majestic.api.dashboard import handle_get_tables
    tables = handle_get_tables()
    assert len(tables) == 1
    t = tables[0]
    assert t["name"] == "notes"
    assert t["rows"] == 1
    assert "title" in t["columns"]
    assert "body" in t["columns"]
    assert "id" not in t["columns"]


def test_get_tables_ignores_non_user_tables(tmp_db):
    con = sqlite3.connect(tmp_db)
    con.execute('CREATE TABLE sessions (id INTEGER PRIMARY KEY, name TEXT)')
    con.commit()
    con.close()

    from majestic.api.dashboard import handle_get_tables
    assert handle_get_tables() == []


# ── handle_create_table ───────────────────────────────────────────────────────

def test_create_table_basic(tmp_db):
    from majestic.api.dashboard import handle_create_table, handle_get_tables
    result = handle_create_table({"name": "tasks", "columns": ["title", "done"]})
    assert result.get("ok") is True

    tables = handle_get_tables()
    assert any(t["name"] == "tasks" for t in tables)


def test_create_table_no_columns_uses_value_column(tmp_db):
    from majestic.api.dashboard import handle_create_table
    result = handle_create_table({"name": "simple", "columns": []})
    assert result.get("ok") is True

    con = sqlite3.connect(tmp_db)
    info = con.execute('PRAGMA table_info("user_simple")').fetchall()
    col_names = [r[1] for r in info]
    assert "value" in col_names
    con.close()


def test_create_table_missing_name_returns_error(tmp_db):
    from majestic.api.dashboard import handle_create_table
    result = handle_create_table({"columns": ["x"]})
    assert "error" in result


# ── handle_delete_table ───────────────────────────────────────────────────────

def test_delete_table(tmp_db):
    from majestic.api.dashboard import handle_create_table, handle_delete_table, handle_get_tables
    handle_create_table({"name": "todrop", "columns": ["x"]})
    assert any(t["name"] == "todrop" for t in handle_get_tables())

    result = handle_delete_table("todrop")
    assert result.get("ok") is True
    assert not any(t["name"] == "todrop" for t in handle_get_tables())


# ── Rows CRUD ─────────────────────────────────────────────────────────────────

def test_add_and_get_rows(tmp_db):
    from majestic.api.dashboard import handle_create_table, handle_add_row, handle_get_rows
    handle_create_table({"name": "items", "columns": ["label", "qty"]})
    result = handle_add_row("items", {"label": "apples", "qty": "5"})
    assert result.get("ok") is True
    assert isinstance(result.get("id"), int)

    rows_data = handle_get_rows("items")
    assert rows_data["columns"] == ["label", "qty"]
    assert len(rows_data["rows"]) == 1
    assert rows_data["rows"][0]["label"] == "apples"
    assert rows_data["rows"][0]["qty"] == "5"


def test_update_row(tmp_db):
    from majestic.api.dashboard import handle_create_table, handle_add_row, handle_update_row, handle_get_rows
    handle_create_table({"name": "fruits", "columns": ["name"]})
    add_result = handle_add_row("fruits", {"name": "banana"})
    row_id = str(add_result["id"])

    upd = handle_update_row("fruits", row_id, {"name": "mango"})
    assert upd.get("ok") is True

    rows = handle_get_rows("fruits")["rows"]
    assert rows[0]["name"] == "mango"


def test_delete_row(tmp_db):
    from majestic.api.dashboard import handle_create_table, handle_add_row, handle_delete_row, handle_get_rows
    handle_create_table({"name": "vegs", "columns": ["name"]})
    add_result = handle_add_row("vegs", {"name": "carrot"})
    row_id = str(add_result["id"])

    del_result = handle_delete_row("vegs", row_id)
    assert del_result.get("ok") is True

    rows = handle_get_rows("vegs")["rows"]
    assert len(rows) == 0


def test_update_row_no_fields_returns_error(tmp_db):
    from majestic.api.dashboard import handle_create_table, handle_add_row, handle_update_row
    handle_create_table({"name": "empty_upd", "columns": ["x"]})
    add_result = handle_add_row("empty_upd", {"x": "hello"})
    row_id = str(add_result["id"])

    result = handle_update_row("empty_upd", row_id, {})
    assert "error" in result


# ── User-table schema injection ───────────────────────────────────────────────

def test_user_tables_schema_in_prompt(tmp_db):
    import sqlite3 as _sqlite3
    con = _sqlite3.connect(tmp_db)
    con.execute('CREATE TABLE "user_books" (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, author TEXT)')
    con.commit()
    con.close()

    from majestic.agent.prompt import _user_tables_schema
    schema = _user_tables_schema()
    assert "user_books" in schema
    assert "title" in schema
    assert "author" in schema


def test_build_system_includes_user_tables(tmp_db):
    import sqlite3 as _sqlite3
    con = _sqlite3.connect(tmp_db)
    con.execute('CREATE TABLE "user_goals" (id INTEGER PRIMARY KEY AUTOINCREMENT, goal TEXT)')
    con.commit()
    con.close()

    from majestic.agent.prompt import build_system
    system = build_system()
    assert "user_goals" in system
    assert "[User tables]" in system


def test_user_tables_schema_empty_when_no_tables(tmp_db):
    from majestic.agent.prompt import _user_tables_schema
    schema = _user_tables_schema()
    assert schema == ""
