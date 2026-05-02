"""File writing tool — write or append content to files in the workspace."""
from majestic.tools.registry import tool


@tool(
    name="write_file",
    description=(
        "Write content to a file. Creates the file if it doesn't exist. "
        "Use when the user asks to save, create, or update a file."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path (absolute, or relative to workspace)",
            },
            "content": {
                "type": "string",
                "description": "Text content to write",
            },
            "append": {
                "type": "boolean",
                "description": "If true, append to existing file instead of overwriting (default false)",
            },
        },
        "required": ["path", "content"],
    },
)
def write_file(path: str, content: str, append: bool = False) -> str:
    from pathlib import Path
    from majestic.constants import WORKSPACE_DIR

    p = Path(path)
    if p.is_absolute():
        # Keep path only if it's already inside WORKSPACE_DIR; otherwise force into workspace
        try:
            p.relative_to(WORKSPACE_DIR)
        except ValueError:
            rel = path.lstrip('/\\')
            p = WORKSPACE_DIR / rel
    else:
        p = WORKSPACE_DIR / path

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        p.write_text(content, encoding="utf-8") if mode == "w" else open(p, "a", encoding="utf-8").write(content)
        action = "Appended to" if append else "Written"
        return f"{action} {p} ({len(content)} chars)"
    except Exception as e:
        return f"Error writing {path}: {e}"
