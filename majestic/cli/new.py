def run(name: str):
    """Create a new profile interactively."""
    from .setup import _init_profile
    from pathlib import Path
    from majestic import display

    display.info(f"Creating new profile: {name}")
    print()
    agent_name = display.ask(f"Agent name", name)
    role = display.ask("Agent role", "General purpose AI assistant")
    tone = display.ask("Tone", "helpful, concise")

    _init_profile(name, agent_name=agent_name)

    display.ok(f"Profile '{name}' created at profiles/{name}/")
    display.info(f"  Role: {role} · Tone: {tone}")
    display.info("Edit profiles/" + name + "/persona.yaml to customize further.")
    display.info("Skills: add YAML files to profiles/" + name + "/skills/")
    display.info("Shared skills: profiles/shared/skills/ — available to all profiles")
