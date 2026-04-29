"""Dashboard-specific API handlers (setup, config, settings, memory, skills, tables, tokens)."""
from __future__ import annotations

import copy
import sqlite3
import time
from pathlib import Path
from typing import Any


# ── Setup ─────────────────────────────────────────────────────────────────────

def handle_setup_status() -> dict:
    from majestic.constants import CONFIG_FILE, MAJESTIC_HOME
    env_file = MAJESTIC_HOME / ".env"
    configured = CONFIG_FILE.exists()
    has_api_key = False
    has_model = False
    if configured:
        try:
            from majestic import config as cfg
            has_api_key = bool(cfg.get("llm.api_key") or _read_env_key(env_file))
            has_model = bool(cfg.get("llm.model"))
        except Exception:
            pass
    return {"configured": configured, "has_api_key": has_api_key, "has_model": has_model}


def handle_setup(body: dict) -> dict:
    from majestic.constants import MAJESTIC_HOME
    MAJESTIC_HOME.mkdir(parents=True, exist_ok=True)

    api_key  = body.get("api_key", "").strip()
    model    = body.get("model", "claude-sonnet-4-6").strip()
    language = body.get("language", "en").strip()
    currency = body.get("currency", "USD").strip()

    env_path = MAJESTIC_HOME / ".env"
    _write_env(env_path, {"ANTHROPIC_API_KEY": api_key})

    config_path = MAJESTIC_HOME / "config.yaml"
    import yaml  # type: ignore[import-untyped]
    cfg_data: dict[str, Any] = {}
    if config_path.exists():
        with open(config_path) as f:
            cfg_data = yaml.safe_load(f) or {}
    cfg_data.setdefault("llm", {})["model"] = model
    cfg_data.setdefault("llm", {})["provider"] = "anthropic"
    cfg_data["language"] = language
    cfg_data["currency"] = currency
    with open(config_path, "w") as f:
        yaml.dump(cfg_data, f, default_flow_style=False, allow_unicode=True)

    return {"ok": True}


# ── Config (simple, for onboarding compat) ────────────────────────────────────

def handle_get_config() -> dict:
    try:
        from majestic import config as cfg
        return {
            "model":       cfg.get("llm.model", ""),
            "language":    cfg.get("language", "en"),
            "currency":    cfg.get("currency", "USD"),
            "search_mode": cfg.get("search_mode", "all"),
        }
    except Exception as e:
        return {"error": str(e)}


def handle_patch_config(body: dict) -> dict:
    try:
        from majestic import config as cfg
        mapping = {
            "model": "llm.model",
            "language": "language",
            "currency": "currency",
            "search_mode": "search_mode",
        }
        for field, key in mapping.items():
            if field in body and body[field]:
                cfg.set_value(key, body[field])
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


# ── Settings (full config.yaml) ───────────────────────────────────────────────

def handle_get_settings() -> dict:
    try:
        from majestic import config as cfg
        from majestic.constants import MAJESTIC_HOME
        data = copy.deepcopy(cfg.load())
        # Redact API key — show only last 4 chars mask
        env_key = _read_env_key(MAJESTIC_HOME / ".env")
        data["_api_key_set"] = bool(env_key)
        data["_api_key_preview"] = (
            "sk-ant-…" + env_key[-4:] if len(env_key) > 8 else ("set" if env_key else "")
        )
        # Remove any raw key from nested llm block if present
        if isinstance(data.get("llm"), dict):
            data["llm"].pop("api_key", None)
        return data
    except Exception as e:
        return {"error": str(e)}


def handle_save_settings(body: dict) -> dict:
    try:
        import yaml  # type: ignore[import-untyped]
        from majestic.constants import CONFIG_FILE, MAJESTIC_HOME

        # Handle API key update separately
        new_key = body.pop("api_key", "").strip()
        body.pop("_api_key_set", None)
        body.pop("_api_key_preview", None)
        if new_key and new_key != "***":
            _write_env(MAJESTIC_HOME / ".env", {"ANTHROPIC_API_KEY": new_key})

        MAJESTIC_HOME.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            yaml.dump(body, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


# ── Memory (raw markdown) ─────────────────────────────────────────────────────

def handle_get_memory_md() -> dict:
    try:
        from majestic.memory.store import load_memory, load_user
        return {"agent": load_memory(), "user": load_user()}
    except Exception:
        return {"agent": "", "user": ""}


def handle_save_memory_md(body: dict) -> dict:
    try:
        from majestic.constants import MEMORY_DIR
        from majestic.memory.store import MEMORY_FILE, USER_FILE
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        if "agent" in body:
            MEMORY_FILE.write_text("# Agent Memory\n\n" + body["agent"].strip() + "\n", encoding="utf-8")
        if "user" in body:
            USER_FILE.write_text("# User Profile\n\n" + body["user"].strip() + "\n", encoding="utf-8")
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


# ── Skills ────────────────────────────────────────────────────────────────────

def handle_get_skills() -> list:
    try:
        from majestic.skills.loader import list_skills
        skills = list_skills()
        return [
            {
                "name":        s.get("name", ""),
                "description": s.get("description", ""),
                "tags":        s.get("tags", []),
                "source":      s.get("source", "user"),
                "usage_count": s.get("usage_count", 0),
                "builtin":     s.get("source") not in ("user", "agent"),
            }
            for s in skills
        ]
    except Exception:
        return []


def handle_get_skill_detail(name: str) -> dict:
    try:
        from majestic.skills.loader import load_skill
        skill = load_skill(name)
        if not skill:
            return {"error": "not found"}
        return {
            "name":        skill["meta"].get("name", name),
            "description": skill["meta"].get("description", ""),
            "tags":        skill["meta"].get("tags", []),
            "source":      skill["meta"].get("source", "user"),
            "body":        skill.get("body", ""),
        }
    except Exception as e:
        return {"error": str(e)}


def handle_create_skill(body: dict) -> dict:
    name = body.get("name", "").strip()
    description = body.get("description", "").strip()
    skill_body = body.get("body", "").strip()
    tags = [t.strip() for t in body.get("tags", []) if str(t).strip()]
    if not name:
        return {"error": "name required"}
    try:
        from majestic.skills.loader import save_skill
        save_skill(name, description, skill_body, tags=tags, source="user")
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


def handle_delete_skill(name: str) -> dict:
    try:
        from majestic.skills.loader import delete_skill
        ok = delete_skill(name)
        return {"ok": ok}
    except Exception as e:
        return {"error": str(e)}


# ── Tables ────────────────────────────────────────────────────────────────────

def _table_columns(con: sqlite3.Connection, table_name: str) -> list[str]:
    """Return non-id column names for a user table."""
    info = con.execute(f'PRAGMA table_info("{table_name}")').fetchall()  # noqa: S608
    return [row[1] for row in info if row[1] != "id"]


def handle_get_tables() -> list:
    try:
        from majestic.constants import DB_PATH
        con = sqlite3.connect(DB_PATH)
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'user_%'"
        ).fetchall()
        result = []
        for (name,) in rows:
            count = con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]  # noqa: S608
            columns = _table_columns(con, name)
            result.append({"name": name[5:], "rows": count, "columns": columns})
        con.close()
        return result
    except Exception:
        return []


def handle_create_table(body: dict) -> dict:
    name = body.get("name", "").strip().replace(" ", "_")
    columns: list[str] = [c.strip() for c in body.get("columns", []) if c.strip()]
    if not name:
        return {"error": "name required"}
    table_name = f"user_{name}"
    col_defs = ", ".join(f'"{c}" TEXT' for c in columns) if columns else '"value" TEXT'
    try:
        from majestic.constants import DB_PATH
        con = sqlite3.connect(DB_PATH)
        con.execute(f'CREATE TABLE IF NOT EXISTS "{table_name}" (id INTEGER PRIMARY KEY AUTOINCREMENT, {col_defs})')  # noqa: S608
        con.commit()
        con.close()
        return {"ok": True, "table": table_name}
    except Exception as e:
        return {"error": str(e)}


def handle_delete_table(name: str) -> dict:
    table_name = f"user_{name}"
    try:
        from majestic.constants import DB_PATH
        con = sqlite3.connect(DB_PATH)
        con.execute(f'DROP TABLE IF EXISTS "{table_name}"')  # noqa: S608
        con.commit()
        con.close()
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


def handle_get_rows(name: str) -> dict:
    table_name = f"user_{name}"
    try:
        from majestic.constants import DB_PATH
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        columns = _table_columns(con, table_name)
        rows = con.execute(f'SELECT * FROM "{table_name}" ORDER BY id DESC LIMIT 500').fetchall()  # noqa: S608
        con.close()
        return {"columns": columns, "rows": [dict(r) for r in rows]}
    except Exception as e:
        return {"error": str(e), "columns": [], "rows": []}


def handle_add_row(name: str, body: dict) -> dict:
    table_name = f"user_{name}"
    try:
        from majestic.constants import DB_PATH
        con = sqlite3.connect(DB_PATH)
        cols = _table_columns(con, table_name)
        vals = [str(body.get(c, "")) for c in cols]
        placeholders = ", ".join("?" for _ in cols)
        col_names = ", ".join(f'"{c}"' for c in cols)
        cur = con.execute(
            f'INSERT INTO "{table_name}" ({col_names}) VALUES ({placeholders})',  # noqa: S608
            vals,
        )
        con.commit()
        row_id = cur.lastrowid
        con.close()
        return {"ok": True, "id": row_id}
    except Exception as e:
        return {"error": str(e)}


def handle_update_row(name: str, row_id: str, body: dict) -> dict:
    table_name = f"user_{name}"
    try:
        from majestic.constants import DB_PATH
        con = sqlite3.connect(DB_PATH)
        cols = _table_columns(con, table_name)
        updates = [f'"{c}" = ?' for c in cols if c in body]
        vals = [str(body[c]) for c in cols if c in body]
        if not updates:
            return {"error": "no fields to update"}
        vals.append(row_id)
        con.execute(
            f'UPDATE "{table_name}" SET {", ".join(updates)} WHERE id = ?',  # noqa: S608
            vals,
        )
        con.commit()
        con.close()
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


def handle_delete_row(name: str, row_id: str) -> dict:
    table_name = f"user_{name}"
    try:
        from majestic.constants import DB_PATH
        con = sqlite3.connect(DB_PATH)
        con.execute(f'DELETE FROM "{table_name}" WHERE id = ?', (row_id,))  # noqa: S608
        con.commit()
        con.close()
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


# ── Monitoring ─────────────────────────────────────────────────────────────────

def handle_get_monitoring() -> dict:
    from majestic.token_tracker import get_stats
    stats = get_stats()
    history = stats.get("history", [])

    # Aggregate by date
    by_day: dict[str, dict] = {}
    for entry in reversed(history):
        day = entry.get("ts", "")[:10]
        if not day:
            continue
        if day not in by_day:
            by_day[day] = {"date": day, "tokens_in": 0, "tokens_out": 0, "cost": 0.0, "requests": 0}
        by_day[day]["tokens_in"]  += entry.get("in", 0)
        by_day[day]["tokens_out"] += entry.get("out", 0)
        by_day[day]["cost"]       = round(by_day[day]["cost"] + entry.get("cost", 0.0), 6)
        by_day[day]["requests"]   += 1

    schedules: list[dict] = []
    try:
        from majestic.cron.jobs import list_schedules
        schedules = list_schedules()
    except Exception:
        pass

    reminders: list[dict] = []
    try:
        from majestic.reminders import list_reminders
        reminders = list_reminders(include_done=False)
    except Exception:
        pass

    return {
        "tokens": {
            "total_in":      stats.get("tokens_in", 0),
            "total_out":     stats.get("tokens_out", 0),
            "total_cost_usd": stats.get("cost_usd", 0.0),
            "requests":      stats.get("requests", 0),
            "by_day":        list(by_day.values()),
        },
        "schedules": schedules,
        "reminders": reminders,
    }


def handle_delete_schedule(schedule_id: str) -> dict:
    try:
        from majestic.cron.jobs import remove_schedule
        ok = remove_schedule(int(schedule_id))
        return {"ok": ok}
    except Exception as e:
        return {"error": str(e)}


# ── Token stats ───────────────────────────────────────────────────────────────

def handle_token_stats() -> dict:
    try:
        from majestic.token_tracker import get_stats
        stats = get_stats()
        return {
            "total_tokens": stats.get("total_tokens", 0),
            "total_cost_usd": stats.get("cost_usd", 0.0),
            "sessions": stats.get("sessions", 0),
        }
    except Exception:
        return {"total_tokens": 0, "total_cost_usd": 0.0, "sessions": 0}


# ── Sessions / messages ───────────────────────────────────────────────────────

def handle_get_sessions() -> list:
    try:
        from majestic.db.state import StateDB
        rows = StateDB().get_recent_sessions(limit=50)
        result = []
        for r in rows:
            result.append({
                "id":            str(r.get("id", "")),
                "title":         r.get("title") or None,
                "source":        r.get("source", "") or "",
                "started_at":    r.get("started_at", "") or r.get("created_at", ""),
                "message_count": r.get("message_count", 0),
            })
        return result
    except Exception:
        return []


def handle_create_session(body: dict) -> dict:
    try:
        from majestic.db.state import StateDB
        db = StateDB()
        name = body.get("name") or "New Chat"
        sid = db.create_session(source=name)
        return {
            "id": str(sid),
            "title": None,
            "source": name,
            "started_at": "",
            "message_count": 0,
        }
    except Exception as e:
        return {"error": str(e)}


def handle_delete_session(session_id: str) -> dict:
    try:
        from majestic.db.state import StateDB
        db = StateDB()
        db._conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        db._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        db._conn.commit()
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


def handle_get_messages(session_id: str) -> list:
    try:
        from majestic.db.state import StateDB
        rows = StateDB().get_session_messages(session_id=session_id)
        return [
            {
                "id":         str(i),
                "role":       r.get("role", "user"),
                "content":    r.get("content", ""),
                "created_at": r.get("timestamp", ""),
            }
            for i, r in enumerate(rows)
        ]
    except Exception:
        return []


# ── Internal helpers ──────────────────────────────────────────────────────────

def _read_env_key(path: Path) -> str:
    if not path.exists():
        return ""
    for line in path.read_text().splitlines():
        if line.startswith("ANTHROPIC_API_KEY="):
            return line.split("=", 1)[1].strip()
    return ""


def _write_env(path: Path, kv: dict[str, str]) -> None:
    existing: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                existing[k.strip()] = v.strip()
    existing.update(kv)
    path.write_text("\n".join(f"{k}={v}" for k, v in existing.items()) + "\n")
