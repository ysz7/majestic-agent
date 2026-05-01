"""LLM configuration manager — save, load, and activate named LLM configurations."""
from __future__ import annotations

import re
from pathlib import Path


def _key_env_name(name: str) -> str:
    return "LLM_KEY_" + re.sub(r"[^A-Z0-9]", "_", name.upper())


def _read_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                result[k.strip()] = v.strip()
    return result


def _write_env(path: Path, updates: dict[str, str]) -> None:
    existing = _read_env(path)
    existing.update(updates)
    path.write_text(
        "\n".join(f"{k}={v}" for k, v in existing.items()) + "\n",
        encoding="utf-8",
    )


def _load_cfg() -> tuple[dict, Path]:
    import yaml
    from majestic.constants import CONFIG_FILE
    cfg_data: dict = {}
    if CONFIG_FILE.exists():
        cfg_data = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")) or {}
    return cfg_data, CONFIG_FILE


def _save_cfg(cfg_data: dict, path: Path) -> None:
    import yaml
    path.write_text(
        yaml.dump(cfg_data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def handle_get_llm_configs() -> list:
    try:
        cfg_data, _ = _load_cfg()
        llm = cfg_data.get("llm", {})
        active = llm.get("active_config", "")
        return [
            {
                "name":        c.get("name", ""),
                "provider":    c.get("provider", ""),
                "model":       c.get("model", ""),
                "key_preview": c.get("key_preview", ""),
                "ollama_url":  c.get("ollama_url", ""),
                "active":      c.get("name", "") == active,
            }
            for c in llm.get("configs", [])
        ]
    except Exception:
        return []


def handle_create_llm_config(body: dict) -> dict:
    try:
        from majestic.constants import MAJESTIC_HOME
        name       = body.get("name", "").strip()
        provider   = body.get("provider", "").strip()
        model      = body.get("model", "").strip()
        api_key    = body.get("api_key", "").strip()
        ollama_url = body.get("ollama_url", "").strip()

        if not name:
            return {"error": "name required"}
        if not provider:
            return {"error": "provider required"}

        key_preview = ""
        if api_key:
            key_preview = api_key[:7] + "…" + api_key[-4:] if len(api_key) > 11 else "***"
            _write_env(MAJESTIC_HOME / ".env", {_key_env_name(name): api_key})

        cfg_data, cfg_path = _load_cfg()
        llm = cfg_data.setdefault("llm", {})
        configs = [c for c in llm.get("configs", []) if c.get("name") != name]
        entry: dict = {"name": name, "provider": provider, "model": model, "key_preview": key_preview}
        if ollama_url:
            entry["ollama_url"] = ollama_url
        configs.append(entry)
        llm["configs"] = configs
        _save_cfg(cfg_data, cfg_path)
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


def handle_delete_llm_config(name: str) -> dict:
    try:
        from majestic.constants import MAJESTIC_HOME
        cfg_data, cfg_path = _load_cfg()
        llm = cfg_data.setdefault("llm", {})
        llm["configs"] = [c for c in llm.get("configs", []) if c.get("name") != name]
        if llm.get("active_config") == name:
            llm.pop("active_config", None)
        _save_cfg(cfg_data, cfg_path)

        env_path = MAJESTIC_HOME / ".env"
        if env_path.exists():
            env_key = _key_env_name(name)
            lines = [ln for ln in env_path.read_text(encoding="utf-8").splitlines()
                     if not ln.startswith(env_key + "=")]
            env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


def handle_activate_llm_config(name: str) -> dict:
    try:
        from majestic.constants import MAJESTIC_HOME
        cfg_data, cfg_path = _load_cfg()
        llm = cfg_data.setdefault("llm", {})
        target = next((c for c in llm.get("configs", []) if c.get("name") == name), None)
        if not target:
            return {"error": "config not found"}

        llm["provider"]      = target["provider"]
        llm["model"]         = target.get("model", "")
        llm["active_config"] = name
        if target.get("ollama_url"):
            llm["ollama_url"] = target["ollama_url"]

        # Copy stored API key to the native env var — both on disk and in the running process
        import os
        env_path = MAJESTIC_HOME / ".env"
        api_key = _read_env(env_path).get(_key_env_name(name), "")
        if api_key:
            native = {"anthropic": "ANTHROPIC_API_KEY", "openrouter": "OPENROUTER_API_KEY"}.get(
                target["provider"], ""
            )
            if native:
                _write_env(env_path, {native: api_key})
                os.environ[native] = api_key  # update running process immediately

        _save_cfg(cfg_data, cfg_path)
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}
