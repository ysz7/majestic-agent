"""Execute Python code in a subprocess and return stdout/stderr."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

from majestic.tools.registry import tool


@tool(
    name="run_python",
    description=(
        "Execute Python code and return stdout/stderr output. "
        "Use for calculations, data analysis, CSV processing, generating charts, "
        "or verifying logic before writing to a file. "
        "Files created during execution are saved to the workspace."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code to execute",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 30)",
            },
        },
        "required": ["code"],
    },
)
def run_python(code: str, timeout: int = 30) -> str:
    from majestic.constants import WORKSPACE_DIR
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", encoding="utf-8", delete=False) as f:
        f.write(textwrap.dedent(code))
        tmp = Path(f.name)

    try:
        result = subprocess.run(
            [sys.executable, str(tmp)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(WORKSPACE_DIR),
        )
        parts: list[str] = []
        if result.stdout.strip():
            parts.append(result.stdout.rstrip())
        if result.stderr.strip():
            parts.append(f"[stderr]\n{result.stderr.rstrip()}")
        if result.returncode != 0:
            parts.append(f"[exit code: {result.returncode}]")
        return "\n".join(parts) if parts else "(no output)"
    except subprocess.TimeoutExpired:
        return f"[timeout] Code execution exceeded {timeout}s"
    except Exception as e:
        return f"[error] {e}"
    finally:
        tmp.unlink(missing_ok=True)
