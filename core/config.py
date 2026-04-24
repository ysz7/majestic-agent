"""
Shared agent config — persisted to data/config.json.

Keys:
  lang      — LLM response language, e.g. "EN", "RU" (default: "EN")
  currency  — currency for prices in LLM output, e.g. "USD", "EUR" (default: "USD")
  mod       — RAG search scope: "all" | "docs" | "intel" (default: "all")
              all   — search across all indexed sources (documents + intel)
              docs  — search only in locally uploaded documents
              intel — search only in collected research (HN, Reddit, GitHub, RSS...)
"""
import json
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent.parent / "data" / "config.json"

_DEFAULTS: dict = {
    "lang":     "EN",
    "currency": "USD",
    "mod":      "all",
}

_VALID_MODS = {"all", "docs", "intel"}


def _load() -> dict:
    if _CONFIG_PATH.exists():
        try:
            return {**_DEFAULTS, **json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))}
        except Exception:
            pass
    return dict(_DEFAULTS)


def _save(cfg: dict):
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def get_lang() -> str:
    """Return current response language (e.g. 'EN', 'RU')."""
    return _load().get("lang", "EN").upper()


def set_lang(lang: str):
    """Set LLM response language. lang should be a 2-letter ISO code like 'EN' or 'RU'."""
    cfg = _load()
    cfg["lang"] = lang.upper()
    _save(cfg)


def get_currency() -> str:
    """Return current currency code (e.g. 'USD', 'EUR')."""
    return _load().get("currency", "USD").upper()


def set_currency(currency: str):
    """Set currency for prices in LLM output."""
    cfg = _load()
    cfg["currency"] = currency.upper()
    _save(cfg)


def get_mod() -> str:
    """Return current RAG search scope: 'all', 'docs', or 'intel'."""
    val = _load().get("mod", "all").lower()
    return val if val in _VALID_MODS else "all"


def set_mod(mod: str):
    """Set RAG search scope. Must be one of: all, docs, intel."""
    mod = mod.lower()
    if mod not in _VALID_MODS:
        raise ValueError(f"Invalid mod '{mod}'. Choose from: {', '.join(sorted(_VALID_MODS))}")
    cfg = _load()
    cfg["mod"] = mod
    _save(cfg)


def get(key: str, default=None):
    return _load().get(key, default)


def set_value(key: str, value):
    cfg = _load()
    cfg[key] = value
    _save(cfg)
