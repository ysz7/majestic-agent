def run():
    """Interactive setup wizard. Prompts for API keys and default profile settings."""
    print("\nWelcome to Majestic! Let's get you set up.\n")

    # LLM Providers
    print("── LLM Providers ───────────────────────────")
    openrouter_key = input("? OpenRouter API key (primary): ").strip()
    anthropic_key = input("? Anthropic API key (fallback 1, press Enter to skip): ").strip()
    openai_key = input("? OpenAI API key (fallback 2, press Enter to skip): ").strip()

    # Web Search
    print("\n── Web Search ──────────────────────────────")
    brave_key = input("? Brave Search API key (press Enter to use DuckDuckGo free fallback): ").strip()

    # Default Profile
    print("\n── Default Profile Setup ───────────────────")
    agent_name = input("? Agent name [Assistant]: ").strip() or "Assistant"
    language = input("? Language [en]: ").strip() or "en"

    print("\n  Model suggestions:")
    print("  Reasoning: anthropic/claude-sonnet-4-5")
    print("  Simple:    meta-llama/llama-3.1-8b-instruct:free")
    print("  Code:      qwen/qwen-2.5-coder-32b-instruct")
    print("  Reflection: meta-llama/llama-3.1-8b-instruct:free")

    reason_model = input("? Model for reasoning [anthropic/claude-sonnet-4-5]: ").strip() or "anthropic/claude-sonnet-4-5"
    simple_model = input("? Model for simple tasks [meta-llama/llama-3.1-8b-instruct:free]: ").strip() or "meta-llama/llama-3.1-8b-instruct:free"
    code_model = input("? Model for code [qwen/qwen-2.5-coder-32b-instruct]: ").strip() or "qwen/qwen-2.5-coder-32b-instruct"
    reflection_model = input("? Model for reflection [meta-llama/llama-3.1-8b-instruct:free]: ").strip() or "meta-llama/llama-3.1-8b-instruct:free"

    print("\n── Limits (optional) ───────────────────────")
    max_tokens = input("? Max tokens per task (0 = unlimited) [0]: ").strip() or "0"
    max_cost = input("? Max cost per task in USD (0 = unlimited) [0]: ").strip() or "0"

    # Write files
    _write_profile("default", {
        "openrouter_key": openrouter_key,
        "anthropic_key": anthropic_key,
        "openai_key": openai_key,
        "brave_key": brave_key,
        "agent_name": agent_name,
        "language": language,
        "reason_model": reason_model,
        "simple_model": simple_model,
        "code_model": code_model,
        "reflection_model": reflection_model,
        "max_tokens": max_tokens,
        "max_cost": max_cost,
    })

    print("\n── Done! ───────────────────────────────────")
    print("✓ profiles/default/.env created")
    print("✓ profiles/default/persona.yaml created")
    print("✓ profiles/default/workspace/ initialized")
    print("✓ profiles/default/data/ initialized")

    start = input("\nStart the agent now? (y/n) [n]: ").strip().lower()
    if start == "y":
        from majestic.cli.foreground import run as fg_run
        fg_run("default")


def _write_profile(profile_name: str, config: dict):
    """Write .env and persona.yaml for a profile."""
    import yaml
    from pathlib import Path

    profile_dir = Path(f"profiles/{profile_name}")
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "workspace/tools").mkdir(parents=True, exist_ok=True)
    (profile_dir / "workspace/output").mkdir(parents=True, exist_ok=True)
    (profile_dir / "workspace/temp").mkdir(parents=True, exist_ok=True)
    (profile_dir / "data").mkdir(parents=True, exist_ok=True)
    (profile_dir / "skills").mkdir(parents=True, exist_ok=True)

    env_lines = [f"OPENROUTER_API_KEY={config['openrouter_key']}"]
    if config["anthropic_key"]:
        env_lines.append(f"ANTHROPIC_API_KEY={config['anthropic_key']}")
    if config["openai_key"]:
        env_lines.append(f"OPENAI_API_KEY={config['openai_key']}")
    if config["brave_key"]:
        env_lines.append(f"BRAVE_SEARCH_API_KEY={config['brave_key']}")
    env_lines.append("AGENT_PORT=8000")
    (profile_dir / ".env").write_text("\n".join(env_lines))

    persona = {
        "name": config["agent_name"],
        "role": "General purpose AI assistant",
        "tone": "helpful, concise",
        "language": config["language"],
        "restrictions": [],
        "context": "",
        "model_routing": {
            "reason": config["reason_model"],
            "simple": config["simple_model"],
            "code": config["code_model"],
            "reflection": config["reflection_model"],
        },
        "limits": {
            "max_tokens_per_task": int(config["max_tokens"]),
            "max_cost_per_task": float(config["max_cost"]),
        }
    }
    with open(profile_dir / "persona.yaml", "w") as f:
        yaml.dump(persona, f, default_flow_style=False, allow_unicode=True)
