def run(name: str):
    """Create a new profile interactively."""
    from .setup import _write_profile
    import yaml
    from pathlib import Path

    print(f"\nCreating new profile: {name}\n")
    agent_name = input(f"? Agent name [{name}]: ").strip() or name
    role = input("? Agent role [General purpose AI assistant]: ").strip() or "General purpose AI assistant"
    tone = input("? Tone [helpful, concise]: ").strip() or "helpful, concise"
    port = input("? Agent port [8001]: ").strip() or "8001"

    config = {
        "openrouter_key": "",
        "anthropic_key": "",
        "openai_key": "",
        "brave_key": "",
        "agent_name": agent_name,
        "language": "en",
        "reason_model": "anthropic/claude-sonnet-4-5",
        "simple_model": "meta-llama/llama-3.1-8b-instruct:free",
        "code_model": "qwen/qwen-2.5-coder-32b-instruct",
        "reflection_model": "meta-llama/llama-3.1-8b-instruct:free",
        "max_tokens": "0",
        "max_cost": "0",
    }

    print("\nCopy API keys from default profile? (y/n) [y]: ", end="")
    copy = input().strip().lower()
    if copy != "n":
        default_env = Path("profiles/default/.env")
        if default_env.exists():
            for line in default_env.read_text().splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    if "OPENROUTER" in k: config["openrouter_key"] = v
                    elif "ANTHROPIC" in k: config["anthropic_key"] = v
                    elif "OPENAI" in k: config["openai_key"] = v
                    elif "BRAVE" in k: config["brave_key"] = v

    _write_profile(name, config)

    # Fix port in .env
    env_path = Path(f"profiles/{name}/.env")
    content = env_path.read_text()
    content = content.replace("AGENT_PORT=8000", f"AGENT_PORT={port}")
    env_path.write_text(content)

    print(f"\n✓ Profile '{name}' created at profiles/{name}/")
