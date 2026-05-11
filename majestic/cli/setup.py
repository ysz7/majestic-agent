"""
majestic setup — first-run wizard.

Asks for ONE LLM provider key and creates the root .env + default profile.
Everything else (model routing, extra providers) can be added later.
"""

from __future__ import annotations

import sys
from pathlib import Path

from majestic import display

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def run() -> None:
    print()
    display.ok("Welcome to Majestic!")
    display.info("You need ONE key to get started. Add more providers later if needed.")
    print()

    # ── Step 1: pick a provider ──────────────────────────────────────────
    provider = display.choose(
        "Pick your LLM provider:",
        [
            "OpenRouter  (recommended — 200+ models, one key)",
            "Anthropic   (Claude models directly)",
            "OpenAI      (GPT models directly)",
            "Ollama      (local models, no key needed)",
        ],
        default=0,
    )

    env_lines: list[str] = []

    if provider == 0:
        key = display.ask("OpenRouter API key")
        if not key:
            display.err("Key cannot be empty.")
            sys.exit(1)
        env_lines.append(f"OPENROUTER_API_KEY={key}")

    elif provider == 1:
        key = display.ask("Anthropic API key")
        if not key:
            display.err("Key cannot be empty.")
            sys.exit(1)
        env_lines.append(f"ANTHROPIC_API_KEY={key}")

    elif provider == 2:
        key = display.ask("OpenAI API key")
        if not key:
            display.err("Key cannot be empty.")
            sys.exit(1)
        env_lines.append(f"OPENAI_API_KEY={key}")

    else:  # Ollama
        url = display.ask("Ollama base URL", "http://localhost:11434")
        model = display.ask("Default model", "llama3.2")
        env_lines.append(f"OLLAMA_BASE_URL={url}")
        env_lines.append(f"OLLAMA_MODEL={model}")

    # ── Step 2: optional web search ──────────────────────────────────────
    print()
    display.info("Web search key (optional — press Enter to use DuckDuckGo for free):")
    brave = display.ask("Brave Search API key", "")
    if brave:
        env_lines.append(f"BRAVE_SEARCH_API_KEY={brave}")

    # ── Step 3: agent name ───────────────────────────────────────────────
    print()
    name = display.ask("Agent name", "Assistant")

    # ── Write root .env ──────────────────────────────────────────────────
    root_env = _PROJECT_ROOT / ".env"
    root_env.write_text("\n".join(env_lines) + "\n", encoding="utf-8")

    # ── Write default profile ────────────────────────────────────────────
    _init_profile("default", agent_name=name)

    print()
    display.ok(".env created")
    display.ok("profiles/default/ ready")
    print()
    display.info("Start the agent:")
    display.info("  majestic             — interactive session")
    display.info("  majestic run default — background daemon")
    print()

    start = display.ask("Start now?", "n")
    if start.lower() == "y":
        from majestic.cli.foreground import run as fg_run
        fg_run("default")


def _init_profile(profile_name: str, agent_name: str = "Assistant") -> None:
    """Create the profile directory structure and minimal persona.yaml."""
    import yaml

    profile_dir = _PROJECT_ROOT / "profiles" / profile_name
    for sub in ("workspace/tools", "workspace/output", "workspace/temp", "data", "skills"):
        (profile_dir / sub).mkdir(parents=True, exist_ok=True)

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
