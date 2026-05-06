"""Agent Script Library — save, list, and run reusable scripts."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
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
        if cfg.get("agent.allow_scripts") is False:
            return "Script execution is disabled (agent.allow_scripts: false)."
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



def _validate_syntax(code: str) -> str | None:
    """Return error string if code has a syntax error, else None."""
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp = f.name
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", tmp],
            capture_output=True, text=True, timeout=10,
        )
        Path(tmp).unlink(missing_ok=True)
        if result.returncode != 0:
            return result.stderr.strip() or "Syntax error"
    except Exception:
        pass
    return None


_STR  = {"type": "string"}
_SARR = {"type": "array", "items": _STR}


@tool(
    name="save_script",
    description="Save a reusable Python script to workspace/scripts/. Run with run_script.",
    input_schema={
        "type": "object",
        "properties": {
            "name":        {**_STR,  "description": "Script name without .py (e.g. 'currency_rate')"},
            "description": {**_STR,  "description": "One-line description"},
            "code":        {**_STR,  "description": "Python code"},
            "params":      {**_SARR, "description": "Param names injected as env vars"},
            "requires":    {**_SARR, "description": "PyPI packages needed (e.g. ['requests'])"},
            "tags":        {**_SARR, "description": "Optional tags"},
        },
        "required": ["name", "description", "code"],
    },
)
def save_script(
    name: str,
    description: str,
    code: str,
    params: list[str] | None = None,
    requires: list[str] | None = None,
    tags: list[str] | None = None,
) -> str:
    err = _check_allowed()
    if err:
        return err

    safe = _safe_name(name)
    if not safe:
        return "Invalid script name."

    syntax_err = _validate_syntax(code)
    if syntax_err:
        return f"Syntax error — not saved:\n{syntax_err}"

    params_str   = ", ".join(params)   if params   else ""
    requires_str = ", ".join(requires) if requires else ""
    tags_str     = ", ".join(tags)     if tags     else ""
    created      = datetime.now().strftime("%Y-%m-%d")

    header = "\n".join([
        f"# description: {description}",
        f"# params: {params_str}",
        f"# requires: {requires_str}",
        f"# tags: {tags_str}",
        f"# created: {created}",
        "# auto_heal: true",
        "",
    ])

    path = _scripts_dir() / f"{safe}.py"
    path.write_text(header + code.strip() + "\n", encoding="utf-8")
    return f"Saved: scripts/{safe}.py"


@tool(
    name="list_scripts",
    description="List all saved scripts in workspace/scripts/ with their descriptions and usage stats.",
    input_schema={"type": "object", "properties": {}},
)
def list_scripts() -> str:
    d = _scripts_dir()
    scripts = sorted(d.glob("*.py"))
    if not scripts:
        return "No scripts saved yet. Use save_script to create one."

    rows = []
    for p in scripts:
        meta    = _parse_frontmatter(p)
        desc    = meta.get("description", "")
        params  = meta.get("params", "")
        created = meta.get("created", "")
        rows.append(f"- {p.stem}: {desc} | params: [{params}] | {created}")
    return "\n".join(rows)


@tool(
    name="run_script",
    description="Run a saved script from workspace/scripts/. Parameters injected as env vars.",
    input_schema={
        "type": "object",
        "properties": {
            "name":    {**_STR,                    "description": "Script name without .py"},
            "params":  {"type": "object",          "description": "Key-value pairs as env vars"},
            "timeout": {"type": "integer",         "description": "Timeout seconds (default 30, max 120)"},
        },
        "required": ["name"],
    },
)
def run_script(name: str, params: dict | None = None, timeout: int = 30) -> str:
    err = _check_allowed()
    if err:
        return err

    d    = _scripts_dir()
    safe = _safe_name(name)
    path = d / f"{safe}.py"

    if not path.exists():
        available = [p.stem for p in sorted(d.glob("*.py"))]
        return f"Script '{name}' not found. Available: {', '.join(available) or 'none'}"

    meta = _parse_frontmatter(path)

    # Dependency check
    requires_str = meta.get("requires", "")
    if requires_str:
        pkgs    = [p.strip() for p in requires_str.split(",") if p.strip()]
        missing = [
            p for p in pkgs
            if importlib.util.find_spec(p.split("[")[0].replace("-", "_")) is None
        ]
        if missing:
            try:
                from majestic import config as cfg
                auto_install = cfg.get("agent.auto_install_deps", True)
            except Exception:
                auto_install = True
            if auto_install:
                for pkg in missing:
                    subprocess.run(
                        [sys.executable, "-m", "pip", "install", pkg],
                        capture_output=True, timeout=60,
                    )
            else:
                return (
                    f"Missing packages: {', '.join(missing)}. "
                    f"Run: pip install {' '.join(missing)}"
                )

    env = {**os.environ}
    if params:
        for k, v in params.items():
            env[str(k)] = str(v)

    timeout = min(max(1, timeout), 120)
    try:
        result = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True, text=True,
            timeout=timeout, env=env,
            cwd=str(d.parent),
        )
        parts = []
        if result.stdout:
            parts.append(f"stdout:\n{result.stdout.strip()}")
        if result.stderr:
            parts.append(f"stderr:\n{result.stderr.strip()}")
        parts.append(f"exit code: {result.returncode}")
        output = "\n\n".join(parts) or "(no output)"

        if result.returncode != 0 and meta.get("auto_heal", "true") != "false":
            output += (
                "\n\n[AUTO-HEAL] Script failed. Analyse the error above, "
                "patch it via save_script, then retry run_script. "
                "You may attempt up to 2 more fixes before giving up."
            )
        return output
    except subprocess.TimeoutExpired:
        return f"Script timed out after {timeout}s."
    except Exception as e:
        return f"Error: {e}"


