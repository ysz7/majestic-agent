"""Agent Script Library — save, list, and run reusable scripts."""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from majestic.tools.registry import tool


def _scripts_dir() -> Path:
    from majestic.constants import WORKSPACE_DIR
    d = WORKSPACE_DIR / "scripts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _check_allowed() -> str | None:
    try:
        from majestic import config as cfg
        if not cfg.get("agent.allow_scripts"):
            return (
                "Script execution is disabled. "
                "Set agent.allow_scripts: true in config to enable."
            )
    except Exception:
        pass
    return None


def _parse_frontmatter(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.rstrip()
                if not line.startswith("# "):
                    break
                if ": " in line:
                    key, _, val = line[2:].partition(": ")
                    result[key.strip()] = val.strip()
    except Exception:
        pass
    return result


def _safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in name.strip())


@tool(
    name="save_script",
    description=(
        "Save a reusable Python script to workspace/scripts/. "
        "Use to store logic you or the user may want to reuse later. "
        "Run with run_script."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Script name without .py (e.g. 'currency_rate')",
            },
            "description": {
                "type": "string",
                "description": "One-line description of what the script does",
            },
            "code": {
                "type": "string",
                "description": "Python code for the script body",
            },
            "params": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Parameter names injected as env vars (e.g. ['from_currency', 'to_currency'])",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional tags",
            },
        },
        "required": ["name", "description", "code"],
    },
)
def save_script(
    name: str,
    description: str,
    code: str,
    params: list[str] | None = None,
    tags: list[str] | None = None,
) -> str:
    err = _check_allowed()
    if err:
        return err

    safe = _safe_name(name)
    if not safe:
        return "Invalid script name."

    params_str = ", ".join(params) if params else ""
    tags_str = ", ".join(tags) if tags else ""
    created = datetime.now().strftime("%Y-%m-%d")

    header = "\n".join([
        f"# description: {description}",
        f"# params: {params_str}",
        f"# tags: {tags_str}",
        f"# created: {created}",
        "",
    ])

    path = _scripts_dir() / f"{safe}.py"
    path.write_text(header + code.strip() + "\n", encoding="utf-8")
    return f"Saved: scripts/{safe}.py"


@tool(
    name="list_scripts",
    description="List all saved scripts in workspace/scripts/ with their descriptions.",
    input_schema={"type": "object", "properties": {}},
)
def list_scripts() -> str:
    d = _scripts_dir()
    scripts = sorted(d.glob("*.py"))
    if not scripts:
        return "No scripts saved yet. Use save_script to create one."

    rows = []
    for p in scripts:
        meta = _parse_frontmatter(p)
        desc = meta.get("description", "")
        params = meta.get("params", "")
        created = meta.get("created", "")
        rows.append(f"- {p.stem}: {desc} | params: [{params}] | {created}")
    return "\n".join(rows)


@tool(
    name="run_script",
    description=(
        "Run a saved script from workspace/scripts/ with optional parameters. "
        "Parameters are injected as environment variables."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Script name without .py",
            },
            "params": {
                "type": "object",
                "description": "Key-value pairs injected as env vars",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 30, max: 120)",
            },
        },
        "required": ["name"],
    },
)
def run_script(name: str, params: dict | None = None, timeout: int = 30) -> str:
    err = _check_allowed()
    if err:
        return err

    d = _scripts_dir()
    path = d / f"{_safe_name(name)}.py"

    if not path.exists():
        available = [p.stem for p in sorted(d.glob("*.py"))]
        return f"Script '{name}' not found. Available: {', '.join(available) or 'none'}"

    env = {**os.environ}
    if params:
        for k, v in params.items():
            env[str(k)] = str(v)

    timeout = min(max(1, timeout), 120)
    try:
        result = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=str(d.parent),
        )
        parts = []
        if result.stdout:
            parts.append(f"stdout:\n{result.stdout.strip()}")
        if result.stderr:
            parts.append(f"stderr:\n{result.stderr.strip()}")
        parts.append(f"exit code: {result.returncode}")
        return "\n\n".join(parts) or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Script timed out after {timeout}s."
    except Exception as e:
        return f"Error: {e}"
