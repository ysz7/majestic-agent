"""
majestic setup — first-run wizard.

Asks for ONE LLM provider key and creates the root .env + default profile.
Everything else (model routing, extra providers) can be added later.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def run() -> None:
    print("\nWelcome to Majestic!\n")
    print("You need ONE key to get started. Add more providers later if needed.")
    print("─" * 52)

    # ── Step 1: pick a provider ──────────────────────────────────────────
    print("\nPick your LLM provider:")
    print("  1  OpenRouter  (recommended — 200+ models, one key)")
    print("     Get key: https://openrouter.ai/keys")
    print("  2  Anthropic   (Claude models directly)")
    print("  3  OpenAI      (GPT models directly)")
    print("  4  Ollama      (local models, no key needed)")
    print()

    while True:
        choice = input("Choice [1]: ").strip() or "1"
        if choice in ("1", "2", "3", "4"):
            break
        print("  Enter 1, 2, 3, or 4.")

    env_lines: list[str] = []

    if choice == "1":
        key = input("OpenRouter API key: ").strip()
        if not key:
            print("Error: key cannot be empty.")
            sys.exit(1)
        env_lines.append(f"OPENROUTER_API_KEY={key}")

    elif choice == "2":
        key = input("Anthropic API key: ").strip()
        if not key:
            print("Error: key cannot be empty.")
            sys.exit(1)
        env_lines.append(f"ANTHROPIC_API_KEY={key}")

    elif choice == "3":
        key = input("OpenAI API key: ").strip()
        if not key:
            print("Error: key cannot be empty.")
            sys.exit(1)
        env_lines.append(f"OPENAI_API_KEY={key}")

    else:  # Ollama
        url = input("Ollama base URL [http://localhost:11434]: ").strip() or "http://localhost:11434"
        model = input("Default model [llama3.2]: ").strip() or "llama3.2"
        env_lines.append(f"OLLAMA_BASE_URL={url}")
        env_lines.append(f"OLLAMA_MODEL={model}")

    # ── Step 2: optional web search ──────────────────────────────────────
    print("\nWeb search key (optional — press Enter to use DuckDuckGo for free):")
    brave = input("Brave Search API key: ").strip()
    if brave:
        env_lines.append(f"BRAVE_SEARCH_API_KEY={brave}")

    # ── Step 3: agent name ───────────────────────────────────────────────
    print()
    name = input("Agent name [Assistant]: ").strip() or "Assistant"

    # ── Write root .env ──────────────────────────────────────────────────
    root_env = _PROJECT_ROOT / ".env"
    root_env.write_text("\n".join(env_lines) + "\n", encoding="utf-8")

    # ── Write default profile ────────────────────────────────────────────
    _init_profile("default", agent_name=name)

    print("\n" + "─" * 52)
    print("✓  .env created")
    print("✓  profiles/default/ ready")
    print("\nStart the agent:")
    print("  majestic             — interactive session")
    print("  majestic run default — background daemon\n")

    start = input("Start now? (y/n) [n]: ").strip().lower()
    if start == "y":
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
