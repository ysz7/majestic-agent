"""
majestic setup — first-run wizard.

Arrow-key navigation via questionary (falls back to number input if not installed).
Flow: provider → key → model → agent name → write root .env → init default profile.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

from majestic import display

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ── Curated model lists (shown when live fetch fails or not applicable) ────────

MODELS_ANTHROPIC = [
    "claude-opus-4-7",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
    "Enter model ID manually",
]

MODELS_OPENAI = [
    "gpt-4o",
    "gpt-4o-mini",
    "o1",
    "o1-mini",
    "Enter model ID manually",
]

MODELS_OPENROUTER_CURATED = [
    # Anthropic (via OpenRouter)
    "anthropic/claude-sonnet-4-6",
    "anthropic/claude-opus-4-7",
    "anthropic/claude-haiku-4-5",
    # OpenAI
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "openai/o3-mini",
    # Google
    "google/gemini-2.5-flash",
    "google/gemini-2.5-pro",
    # DeepSeek
    "deepseek/deepseek-chat",
    "deepseek/deepseek-r1",
    # Mistral
    "mistralai/mistral-large-2411",
    "mistralai/mistral-small-3.1-24b-instruct",
    # Free models
    "meta-llama/llama-3.3-70b-instruct:free",
    "meta-llama/llama-3.1-8b-instruct:free",
    "google/gemma-3-27b-it:free",
    "mistralai/mistral-7b-instruct:free",
    "qwen/qwen3-8b:free",
    "Enter model ID manually",
]

_MANUAL = "Enter model ID manually"


# ── Live model fetchers ────────────────────────────────────────────────────────

def _fetch_ollama_models(base_url: str) -> list[str]:
    """Return list of locally installed Ollama model names.

    Returns [] if Ollama is not reachable.
    """
    try:
        resp = httpx.get(f"{base_url}/api/tags", timeout=3)
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        return []


# ── questionary helpers (graceful fallback) ────────────────────────────────────

def _q_select(prompt: str, choices: list[str], default: str | None = None) -> str:
    """Arrow-key single choice. Falls back to numbered list."""
    try:
        import questionary
        result = questionary.select(prompt, choices=choices, default=default or choices[0]).ask()
        if result is None:
            raise SystemExit(0)
        return result
    except ImportError:
        idx = display.choose(prompt, choices, default=choices.index(default) if default and default in choices else 0)
        return choices[idx]


def _q_password(prompt: str) -> str:
    """Masked password input. Falls back to plain ask."""
    try:
        import questionary
        result = questionary.password(prompt).ask()
        if result is None:
            raise SystemExit(0)
        return result
    except ImportError:
        return display.ask(prompt)


def _q_text(prompt: str, default: str = "") -> str:
    """Plain text input with optional default. Falls back to display.ask."""
    try:
        import questionary
        result = questionary.text(prompt, default=default).ask()
        if result is None:
            raise SystemExit(0)
        return result
    except ImportError:
        return display.ask(prompt, default)


def _q_confirm(prompt: str, default: bool = False) -> bool:
    """Yes/no confirm. Falls back to display.ask."""
    try:
        import questionary
        result = questionary.confirm(prompt, default=default).ask()
        if result is None:
            raise SystemExit(0)
        return result
    except ImportError:
        ans = display.ask(prompt, "y" if default else "n")
        return ans.strip().lower() in ("y", "yes")


# ── Wizard ─────────────────────────────────────────────────────────────────────

def run() -> None:
    print()
    display.ok("Welcome to Majestic!")
    display.info("You need ONE key to get started. Add more providers later if needed.")
    print()

    env_lines: list[str] = []

    # ── Step 1: provider ──────────────────────────────────────────────────
    provider = _q_select(
        "Choose your LLM provider:",
        [
            "OpenRouter  (recommended — 200+ models, one key)",
            "Anthropic   (Claude family)",
            "OpenAI      (GPT family)",
            "Ollama      (local, no key needed)",
        ],
    )

    chosen_model: str = ""

    # ── Step 2: key / URL ────────────────────────────────────────────────
    if provider.startswith("OpenRouter"):
        key = _q_password("OpenRouter API key (will be hidden):")
        if not key:
            display.err("Key cannot be empty.")
            sys.exit(1)
        env_lines.append(f"OPENROUTER_API_KEY={key}")

        # ── Step 3: model ────────────────────────────────────────────────
        chosen_model = _q_select(
            "Choose your main model:", MODELS_OPENROUTER_CURATED, default=MODELS_OPENROUTER_CURATED[0]
        )
        if chosen_model == _MANUAL:
            chosen_model = _q_text("Model ID:")

    elif provider.startswith("Anthropic"):
        key = _q_password("Anthropic API key (will be hidden):")
        if not key:
            display.err("Key cannot be empty.")
            sys.exit(1)
        env_lines.append(f"ANTHROPIC_API_KEY={key}")

        chosen_model = _q_select("Choose your main model:", MODELS_ANTHROPIC, default=MODELS_ANTHROPIC[1])
        if chosen_model == _MANUAL:
            chosen_model = _q_text("Model ID:")

    elif provider.startswith("OpenAI"):
        key = _q_password("OpenAI API key (will be hidden):")
        if not key:
            display.err("Key cannot be empty.")
            sys.exit(1)
        env_lines.append(f"OPENAI_API_KEY={key}")

        chosen_model = _q_select("Choose your main model:", MODELS_OPENAI, default=MODELS_OPENAI[0])
        if chosen_model == _MANUAL:
            chosen_model = _q_text("Model ID:")

    else:  # Ollama
        base_url = _q_text("Ollama base URL:", default="http://localhost:11434")
        env_lines.append(f"OLLAMA_BASE_URL={base_url}")

        ollama_models = _fetch_ollama_models(base_url)
        if not ollama_models:
            display.warn(f"Ollama not reachable at {base_url}. Enter model name manually.")
            chosen_model = _q_text("Model name (e.g. llama3.2):", default="llama3.2")
        else:
            choices = ollama_models + ["Enter manually"]
            chosen_model = _q_select("Choose installed model:", choices, default=choices[0])
            if chosen_model == "Enter manually":
                chosen_model = _q_text("Model name:", default="llama3.2")

        env_lines.append(f"OLLAMA_MODEL={chosen_model}")

    if chosen_model and not provider.startswith("Ollama"):
        env_lines.append(f"MAJESTIC_MODEL_REASON={chosen_model}")

    # ── Step 3: optional Brave Search ────────────────────────────────────
    print()
    display.info("Web search — Brave Search API (optional, press Enter to skip → DuckDuckGo free):")
    brave = _q_text("Brave Search API key:", default="")
    if brave:
        env_lines.append(f"BRAVE_SEARCH_API_KEY={brave}")

    # ── Step 4: agent name ────────────────────────────────────────────────
    print()
    name = _q_text("Agent name:", default="Assistant")
    if name:
        env_lines.append(f"AGENT_NAME={name}")

    # ── Write root .env ───────────────────────────────────────────────────
    root_env = _PROJECT_ROOT / ".env"
    root_env.write_text("\n".join(env_lines) + "\n", encoding="utf-8")

    # ── Init default profile ──────────────────────────────────────────────
    _init_profile("default", agent_name=name or "Assistant")

    print()
    display.ok(".env created")
    display.ok("profiles/default/ ready")
    if chosen_model and not provider.startswith("Ollama"):
        display.ok(f"Main model: {chosen_model}")
    print()
    display.info("Start the agent:")
    display.info("  majestic             — interactive session")
    display.info("  majestic run default — background daemon")
    print()

    if _q_confirm("Start now?", default=False):
        from majestic.cli.foreground import run as fg_run
        fg_run("default")


def _init_profile(profile_name: str, agent_name: str = "Assistant") -> None:
    """Create profile directory structure and minimal persona.yaml.

    Canonical layout
    ----------------
    profiles/<name>/
    ├── persona.yaml          tracked in git
    ├── .env                  gitignored (secrets)
    ├── skills/               tracked — YAML skill definitions
    │   └── .gitkeep
    ├── workspace/
    │   ├── tools/            tracked — promoted reusable scripts
    │   │   └── .gitkeep
    │   ├── output/           gitignored — generated reports / data
    │   └── temp/             gitignored — transient scripts
    └── data/                 gitignored — SQLite databases
    """
    import yaml

    profile_dir = _PROJECT_ROOT / "profiles" / profile_name

    # Gitignored dirs (auto-created at runtime, not tracked)
    for sub in ("workspace/output", "workspace/temp", "data"):
        (profile_dir / sub).mkdir(parents=True, exist_ok=True)

    # Tracked dirs — keep empty with .gitkeep so structure is in git
    for sub in ("skills", "workspace/tools"):
        d = profile_dir / sub
        d.mkdir(parents=True, exist_ok=True)
        gitkeep = d / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()

    persona_file = profile_dir / "persona.yaml"
    if not persona_file.exists():
        persona = {
            "name": agent_name,
            "role": "General purpose AI assistant",
            "tone": "helpful, concise",
            "language": "en",
            "restrictions": [],
            "context": "",
            "limits": {
                "max_tokens_per_task": 0,
                "max_cost_per_task": 0.0,
            },
        }
        with persona_file.open("w", encoding="utf-8") as fh:
            yaml.dump(persona, fh, default_flow_style=False, allow_unicode=True)
