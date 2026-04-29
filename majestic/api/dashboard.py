"""Dashboard-specific API handlers (setup, config, memory, skills, tables, tokens)."""
from __future__ import annotations

import json
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

    # Write .env
    env_path = MAJESTIC_HOME / ".env"
    _write_env(env_path, {"ANTHROPIC_API_KEY": api_key})

    # Write config.yaml
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


# ── Config ────────────────────────────────────────────────────────────────────

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


# ── Memory ────────────────────────────────────────────────────────────────────

def handle_get_memory() -> list:
    try:
        from majestic.memory.store import load_both
        facts, prefs = load_both()
        entries = []
        for k, v in (facts or {}).items():
            entries.append({"key": k, "value": str(v), "scope": "fact"})
        for k, v in (prefs or {}).items():
            entries.append({"key": k, "value": str(v), "scope": "preference"})
        return entries
    except Exception:
        return []


def handle_delete_memory(key: str) -> dict:
    try:
        from majestic.memory.store import forget
        forget(key)
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


# ── Skills ────────────────────────────────────────────────────────────────────

def handle_get_skills() -> list:
    try:
        from majestic.skills.store import load_skills
        skills = load_skills()
        return [
            {
                "name":        s.get("name", ""),
                "description": s.get("description", ""),
                "trigger":     s.get("trigger", s.get("name", "")),
                "enabled":     s.get("enabled", True),
            }
            for s in skills
        ]
    except Exception:
        return []


# ── Tables ────────────────────────────────────────────────────────────────────

def handle_get_tables() -> list:
    try:
        from majestic.constants import DB_PATH
        con = sqlite3.connect(DB_PATH)
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'user_%'"
        ).fetchall()
        result = []
        for (name,) in rows:
            count = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]  # noqa: S608
            result.append({"name": name[5:], "rows": count, "created_at": ""})
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
