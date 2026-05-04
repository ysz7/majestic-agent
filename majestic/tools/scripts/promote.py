"""revert_script and promote_script_to_skill tools."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from majestic.tools.registry import tool


def _scripts_dir() -> Path:
    from majestic.constants import WORKSPACE_DIR
    return WORKSPACE_DIR / "scripts"


def _safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in name.strip())


@tool(
    name="revert_script",
    description=(
        "Revert a script to a previous version from its backup history. "
        "version=-1 means the most recent backup, -2 the one before that, etc."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name":    {"type": "string",  "description": "Script name without .py"},
            "version": {"type": "integer", "description": "-1 = previous version, -2 = one before, etc."},
        },
        "required": ["name"],
    },
)
def revert_script(name: str, version: int = -1) -> str:
    safe = _safe_name(name)
    d    = _scripts_dir()
    hist = d / ".history"

    if not hist.exists():
        return f"No history found for '{safe}'."

    versions = sorted(hist.glob(f"{safe}_*.py"))
    if not versions:
        return f"No backup versions found for '{safe}'."

    try:
        target = versions[version]
    except IndexError:
        return (
            f"Version index {version} out of range. "
            f"Available: {len(versions)} version(s)."
        )

    shutil.copy2(target, d / f"{safe}.py")
    return f"Reverted {safe}.py to {target.name}."


@tool(
    name="promote_script_to_skill",
    description=(
        "Promote a frequently-used script to a slash-command skill so the user can invoke "
        "it as /slash_command. Best for scripts used 5+ times with high success rate."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name":          {"type": "string", "description": "Script name without .py"},
            "slash_command": {"type": "string", "description": "Skill name for /slash_command invocation"},
            "description":   {"type": "string", "description": "Override description (defaults to script description)"},
        },
        "required": ["name", "slash_command"],
    },
)
def promote_script_to_skill(name: str, slash_command: str, description: str = "") -> str:
    from majestic.constants import SKILLS_DIR
    from majestic.tools.scripts.script_tools import _parse_frontmatter

    safe        = _safe_name(name)
    script_path = _scripts_dir() / f"{safe}.py"

    if not script_path.exists():
        return f"Script '{safe}' not found."

    meta  = _parse_frontmatter(script_path)
    desc  = description or meta.get("description", f"Run {safe} script")
    params = meta.get("params", "")
    tags   = meta.get("tags", "script")
    slug   = "".join(
        c if c.isalnum() or c in "_-" else "_"
        for c in slash_command.strip().lstrip("/")
    )

    params_note = f"\nParams (env vars): {params}" if params else ""
    body = (
        f'Use the `run_script` tool with name="{safe}".'
        f"{params_note}\n\n"
        "Pass any user-provided values as the `params` dict. "
        "Return the script output to the user."
    )

    skill_content = (
        f"---\n"
        f"name: {slug}\n"
        f"description: {desc}\n"
        f"tags: [{tags}]\n"
        f"source: promoted\n"
        f"created: {datetime.now().strftime('%Y-%m-%d')}\n"
        f"---\n\n"
        f"{body}\n"
    )

    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    skill_path = SKILLS_DIR / f"{slug}.md"
    skill_path.write_text(skill_content, encoding="utf-8")
    return f"Skill /{slug} created. Users can now invoke it with /{slug}."
