"""
majestic model — change LLM provider and/or model.

  majestic model              change global provider/model (all agents)
  majestic model <profile>    override model for a specific agent profile
"""

from __future__ import annotations

from pathlib import Path

from majestic import display
from majestic.cli.setup import (
    _MANUAL,
    MODELS_ANTHROPIC,
    MODELS_OPENAI,
    MODELS_OPENROUTER_CURATED,
    _fetch_ollama_models,
    _q_confirm,
    _q_password,
    _q_select,
    _q_text,
)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

_PROVIDER_KEY: dict[str, str] = {
    "OpenRouter": "OPENROUTER_API_KEY",
    "Anthropic":  "ANTHROPIC_API_KEY",
    "OpenAI":     "OPENAI_API_KEY",
    "Ollama":     "OLLAMA_BASE_URL",
}

_PROVIDER_MODELS: dict[str, list[str]] = {
    "OpenRouter": MODELS_OPENROUTER_CURATED,
    "Anthropic":  MODELS_ANTHROPIC,
    "OpenAI":     MODELS_OPENAI,
}


# ── .env helpers ──────────────────────────────────────────────────────────────

def _read_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def _write_env(path: Path, data: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in data.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── Provider/model detection ──────────────────────────────────────────────────

def _detect_provider(env: dict[str, str]) -> str | None:
    if env.get("OPENROUTER_API_KEY"):
        return "OpenRouter"
    if env.get("ANTHROPIC_API_KEY"):
        return "Anthropic"
    if env.get("OPENAI_API_KEY"):
        return "OpenAI"
    if env.get("OLLAMA_BASE_URL"):
        return "Ollama"
    return None


def _detect_model(env: dict[str, str], provider: str | None) -> str | None:
    if provider == "Ollama":
        return env.get("OLLAMA_MODEL")
    return env.get("MAJESTIC_MODEL_REASON") or env.get("MAJESTIC_MODEL")


# ── Model picker ──────────────────────────────────────────────────────────────

def _pick_model(provider: str, current: str | None) -> str | None:
    """Show model list for provider; return chosen model or None to cancel."""
    if provider == "Ollama":
        ollama_models = _fetch_ollama_models("http://localhost:11434")
        if not ollama_models:
            display.warn("Ollama not reachable — enter model name manually.")
            return _q_text("Model name:", default=current or "llama3.2") or None
        choices = ollama_models + [_MANUAL, "Cancel"]
        default = current if current in ollama_models else choices[0]
        choice = _q_select("Choose model:", choices, default=default)
    else:
        models = _PROVIDER_MODELS.get(provider, MODELS_OPENROUTER_CURATED)
        choices = list(models) + ["Cancel"]
        default = current if current in models else choices[0]
        choice = _q_select("Choose model:", choices, default=default)

    if choice == "Cancel":
        return None
    if choice == _MANUAL:
        return _q_text("Model ID:", default=current or "") or None
    return choice


# ── Full provider + model flow ────────────────────────────────────────────────

def _provider_flow(env: dict[str, str], env_path: Path,
                   current_provider: str | None, current_model: str | None) -> None:
    """Interactive provider + key + model selection. Writes env_path."""
    provider_choices = [
        "OpenRouter  (recommended — 200+ models, one key)",
        "Anthropic   (Claude family)",
        "OpenAI      (GPT family)",
        "Ollama      (local, no key needed)",
        "Cancel",
    ]
    default_choice = next(
        (c for c in provider_choices if current_provider and c.startswith(current_provider)),
        provider_choices[0],
    )
    raw = _q_select("Choose provider:", provider_choices, default=default_choice)
    if raw == "Cancel":
        return

    provider = raw.split()[0]  # "OpenRouter", "Anthropic", "OpenAI", "Ollama"

    if provider == "Ollama":
        base_url = _q_text(
            "Ollama base URL:",
            default=env.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
        env["OLLAMA_BASE_URL"] = base_url
    else:
        key_name = _PROVIDER_KEY[provider]
        existing = env.get(key_name, "")
        if existing and provider == current_provider:
            keep = _q_confirm(f"Keep existing {key_name}?", default=True)
            if not keep:
                new_key = _q_password(f"New {key_name}:")
                if new_key:
                    env[key_name] = new_key
        else:
            new_key = _q_password(f"{key_name}:")
            if not new_key:
                display.err("Key cannot be empty.")
                return
            env[key_name] = new_key
            # Remove old provider keys when switching
            if provider != current_provider:
                for p, k in _PROVIDER_KEY.items():
                    if p != provider and k != "OLLAMA_BASE_URL":
                        env.pop(k, None)

    new_model = _pick_model(provider, current_model)
    if new_model:
        if provider == "Ollama":
            env["OLLAMA_MODEL"] = new_model
            env.pop("MAJESTIC_MODEL_REASON", None)
        else:
            env["MAJESTIC_MODEL_REASON"] = new_model
            env.pop("OLLAMA_MODEL", None)

    _write_env(env_path, env)
    display.ok(f"Provider: {provider}")
    if new_model:
        display.ok(f"Model:    {new_model}")


# ── Entry points ──────────────────────────────────────────────────────────────

def run(profile_name: str | None = None) -> None:
    is_global = profile_name is None
    env_path  = (
        _PROJECT_ROOT / ".env"
        if is_global
        else _PROJECT_ROOT / "profiles" / profile_name / ".env"
    )
    root_env = _read_env(_PROJECT_ROOT / ".env")
    env      = _read_env(env_path)

    # Merged view: root as baseline, profile on top
    merged           = {**root_env, **env}
    current_provider = _detect_provider(merged)
    current_model    = _detect_model(merged, current_provider)
    scope            = "global" if is_global else f"profile: {profile_name}"

    print()
    display.info(f"Model configuration ({scope})")
    print()
    if current_provider:
        inherited = "" if is_global or _detect_provider(env) else "  (inherited from global)"
        display.info(f"  provider · {current_provider}{inherited}")
        display.info(f"  model    · {current_model or '(default)'}")
    else:
        display.info("  No provider configured yet.")
    print()

    # ── Profile mode ──────────────────────────────────────────────────────────
    if not is_global:
        has_override = bool(_detect_provider(env) or _detect_model(env, None))
        choices = [
            "Change model (keep current provider)",
            "Change provider + model",
            "Clear profile overrides (use global settings)",
            "Exit",
        ]
        if not has_override:
            choices.remove("Clear profile overrides (use global settings)")

        action = _q_select("What would you like to do?", choices)
        if action == "Exit":
            return

        if action == "Clear profile overrides (use global settings)":
            for k in ("MAJESTIC_MODEL_REASON", "MAJESTIC_MODEL", "OLLAMA_MODEL",
                      *_PROVIDER_KEY.values()):
                env.pop(k, None)
            _write_env(env_path, env)
            display.ok("Profile overrides cleared — using global settings.")
            return

        if action == "Change model (keep current provider)":
            if not current_provider:
                display.err("No provider configured globally. Run: majestic model")
                return
            new_model = _pick_model(current_provider, current_model)
            if new_model:
                if current_provider == "Ollama":
                    env["OLLAMA_MODEL"] = new_model
                else:
                    env["MAJESTIC_MODEL_REASON"] = new_model
                _write_env(env_path, env)
                display.ok(f"Model: {new_model}")
            return

        # "Change provider + model"
        _provider_flow(env, env_path, current_provider, current_model)
        return

    # ── Global mode ───────────────────────────────────────────────────────────
    if current_provider:
        choices = [
            f"Keep provider ({current_provider}), change model only",
            "Switch provider",
            f"Clear API key for {current_provider}",
            "Exit",
        ]
    else:
        choices = ["Set up provider", "Exit"]

    action = _q_select("What would you like to change?", choices)
    if action == "Exit":
        return

    if action.startswith("Keep provider"):
        new_model = _pick_model(current_provider, current_model)
        if new_model:
            env["MAJESTIC_MODEL_REASON"] = new_model
            _write_env(env_path, env)
            display.ok(f"Model: {new_model}")
        return

    if action.startswith("Clear API key"):
        key = _PROVIDER_KEY.get(current_provider or "", "")
        if key and _q_confirm(f"Remove {key} from .env?", default=False):
            env.pop(key, None)
            env.pop("MAJESTIC_MODEL_REASON", None)
            env.pop("OLLAMA_MODEL", None)
            _write_env(env_path, env)
            display.ok("API key removed.")
        return

    # "Switch provider" or "Set up provider"
    _provider_flow(env, env_path, current_provider, current_model)
