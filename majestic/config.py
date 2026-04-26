"""
Read/write ~/.majestic-agent/config.yaml and ~/.majestic-agent/.env.
All agent code should use this module instead of reading env vars directly.
"""
import os
import yaml
from pathlib import Path
from typing import Any

from majestic.constants import CONFIG_FILE, ENV_FILE, MAJESTIC_HOME

_DEFAULTS: dict = {
    "llm": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
    },
    "agent": {
        "role": "",
        "tools_enabled": [],
        "tools_disabled": [],
    },
    "api": {
        "port": 8080,
        "key": "",
    },
    "mcp_servers": [],
    "language": "EN",
    "currency": "USD",
    "search_mode": "all",
    "telegram": {
        "morning_briefing_hour": 0,
        "allowed_user_ids": [],
    },
    "research": {
        "auto_interval_minutes": 0,
        "reddit_subs": [],
        "mastodon_instance": "mastodon.social",
        "google_trends_geo": "US",
        "crypto_coins": ["bitcoin", "ethereum", "solana"],
        "stock_symbols": ["AAPL", "NVDA", "MSFT"],
        "forex_pairs": ["EUR", "GBP", "JPY"],
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load() -> dict:
    if not CONFIG_FILE.exists():
        return dict(_DEFAULTS)
    try:
        data = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")) or {}
        return _deep_merge(_DEFAULTS, data)
    except Exception:
        return dict(_DEFAULTS)


def save(cfg: dict) -> None:
    MAJESTIC_HOME.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        yaml.dump(cfg, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def get(key: str, default: Any = None) -> Any:
    """Get a config value by dotted key, e.g. get('llm.provider')."""
    cfg = load()
    parts = key.split(".")
    val = cfg
    for p in parts:
        if not isinstance(val, dict) or p not in val:
            return default
        val = val[p]
    return val


def set_value(key: str, value: Any) -> None:
    """Set a config value by dotted key, e.g. set_value('llm.model', 'claude-opus-4-7')."""
    cfg = load()
    parts = key.split(".")
    node = cfg
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = value
    save(cfg)


def is_configured() -> bool:
    return CONFIG_FILE.exists() and ENV_FILE.exists()


def load_env() -> None:
    """Load ~/.majestic-agent/.env into os.environ (does not override existing vars)."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        if k and k not in os.environ:
            os.environ[k] = v.strip()


def sync_env_from_config() -> None:
    """
    Populate env vars that legacy core/ code expects based on config.yaml.
    Called at agent startup so existing code works with new config location.
    """
    load_env()
    cfg = load()

    provider = cfg.get("llm", {}).get("provider", "anthropic")
    model    = cfg.get("llm", {}).get("model", "claude-sonnet-4-6")
    os.environ.setdefault("LLM_PROVIDER", provider)

    if provider == "anthropic":
        os.environ.setdefault("ANTHROPIC_MODEL", model)
    elif provider == "openai":
        os.environ.setdefault("OPENAI_MODEL", model)
    elif provider == "openrouter":
        os.environ.setdefault("OPENROUTER_MODEL", model)
    else:
        os.environ.setdefault("OLLAMA_MODEL", model)

    lang     = cfg.get("language", "EN")
    currency = cfg.get("currency", "USD")
    os.environ.setdefault("MAJESTIC_LANG", lang)
    os.environ.setdefault("MAJESTIC_CURRENCY", currency)

    tg = cfg.get("telegram", {})
    ids = tg.get("allowed_user_ids", [])
    if ids:
        os.environ.setdefault("TELEGRAM_ALLOWED_USER_ID", ",".join(str(i) for i in ids))
    hour = tg.get("morning_briefing_hour", 0)
    os.environ.setdefault("MORNING_BRIEFING_HOUR", str(hour))

    research = cfg.get("research", {})
    os.environ.setdefault("AUTO_RESEARCH_INTERVAL", str(research.get("auto_interval_minutes", 0)))
    os.environ.setdefault("GOOGLE_TRENDS_GEO", research.get("google_trends_geo", "US"))
