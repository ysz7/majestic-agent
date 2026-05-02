"""File reading tool — read text content from files in the workspace."""
from majestic.tools.registry import tool


@tool(
    name="read_file",
    description=(
        "Read the text content of a file. Supports .txt, .md, .csv, .json, .py, and other text files. "
        "Use when the user asks to read, view, or check a file."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path (absolute, or relative to workspace)",
            },
            "max_lines": {
                "type": "integer",
                "description": "Maximum lines to return (default 200)",
            },
        },
        "required": ["path"],
    },
)
def read_file(path: str, max_lines: int = 200) -> str:
    from pathlib import Path
    from majestic.constants import WORKSPACE_DIR

    p = Path(path)
    if p.is_absolute():
        # If the absolute path doesn't exist, try it as workspace-relative
        # (LLMs often prepend "/" to workspace-relative paths)
        if not p.exists():
            rel = path.lstrip('/\\')
            ws_path = WORKSPACE_DIR / rel
            if ws_path.exists():
                p = ws_path
    else:
        p = WORKSPACE_DIR / path

    if not p.exists():
        return f"File not found: {path}"
    if not p.is_file():
        return f"Not a file: {path}"

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if len(lines) > max_lines:
            return "\n".join(lines[:max_lines]) + f"\n\n... ({len(lines) - max_lines} more lines)"
        return text
    except Exception as e:
        return f"Error reading {path}: {e}"
