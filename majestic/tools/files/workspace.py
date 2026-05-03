"""Workspace CRUD tools — list, search, delete, move, mkdir."""
from __future__ import annotations

from majestic.tools.registry import tool

_TEXT_EXTS = {
    ".txt", ".md", ".csv", ".json", ".yaml", ".yml",
    ".toml", ".py", ".js", ".ts", ".html", ".xml", ".log",
}
_RICH_EXTS = {".pdf", ".docx"}
_ALL_EXTS  = _TEXT_EXTS | _RICH_EXTS


def _ws() -> "Path":
    from majestic.constants import WORKSPACE_DIR
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    return WORKSPACE_DIR


def _resolve(path: str) -> "Path":
    from pathlib import Path
    p = Path(path)
    if not p.is_absolute():
        p = _ws() / path
    return p.resolve()


def _safe(p: "Path") -> bool:
    """Ensure path stays inside workspace."""
    try:
        p.relative_to(_ws().resolve())
        return True
    except ValueError:
        return False


def _read_any(p: "Path", max_chars: int = 4000) -> str:
    if p.suffix.lower() in _RICH_EXTS:
        try:
            from majestic.db.parser import load_and_chunk
            chunks = load_and_chunk(p)
            text = " ".join(c.get("text", "") for c in chunks)
            return text[:max_chars] + ("…" if len(text) > max_chars else "")
        except Exception as e:
            return f"[parse error: {e}]"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        return text[:max_chars] + ("…" if len(text) > max_chars else "")
    except Exception as e:
        return f"[read error: {e}]"


def workspace_tree(root: "Path", prefix: str = "", max_depth: int = 4, _depth: int = 0) -> list[str]:
    if _depth > max_depth:
        return []
    lines = []
    try:
        entries = sorted(root.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
    except PermissionError:
        return []
    for i, entry in enumerate(entries):
        connector = "└── " if i == len(entries) - 1 else "├── "
        lines.append(prefix + connector + entry.name + ("/" if entry.is_dir() else ""))
        if entry.is_dir():
            ext = "    " if i == len(entries) - 1 else "│   "
            lines.extend(workspace_tree(entry, prefix + ext, max_depth, _depth + 1))
    return lines


@tool(
    name="workspace_list",
    description=(
        "List files and folders in the workspace. "
        "Returns a tree view. Use 'path' to list a subfolder."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Subfolder path (default: workspace root)"},
        },
    },
)
def workspace_list(path: str = "") -> str:
    root = _resolve(path) if path else _ws()
    if not root.exists():
        return f"Not found: {path}"
    if not _safe(root):
        return "Path outside workspace."
    if root.is_file():
        return _read_any(root)
    lines = [f"workspace/{path}/".rstrip("/")] + workspace_tree(root)
    if not lines[1:]:
        return "Workspace is empty."
    return "\n".join(lines)


@tool(
    name="workspace_search",
    description=(
        "Full-text search across all files in the workspace. "
        "Returns matching excerpts with file paths. "
        "Use when the user asks to find information in their documents."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search keyword or phrase"},
            "path":  {"type": "string", "description": "Limit search to a subfolder (optional)"},
        },
        "required": ["query"],
    },
)
def workspace_search(query: str, path: str = "") -> str:
    import re
    root = _resolve(path) if path else _ws()
    if not _safe(root):
        return "Path outside workspace."

    q_lower = query.lower()
    results: list[str] = []
    for f in sorted(root.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in _ALL_EXTS:
            continue
        text = _read_any(f, max_chars=20000)
        if q_lower not in text.lower():
            continue
        rel  = f.relative_to(_ws())
        # find up to 3 excerpts
        hits = []
        for m in re.finditer(re.escape(query), text, re.IGNORECASE):
            start = max(0, m.start() - 80)
            end   = min(len(text), m.end() + 80)
            hits.append("…" + text[start:end].replace("\n", " ") + "…")
            if len(hits) >= 3:
                break
        results.append(f"📄 {rel}\n" + "\n".join(f"  {h}" for h in hits))
        if len(results) >= 10:
            break

    if not results:
        return f"No matches for '{query}' in workspace."
    return f"Found in {len(results)} file(s):\n\n" + "\n\n".join(results)


@tool(
    name="workspace_delete",
    description="Delete a file or empty folder from the workspace.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File or folder path to delete"},
        },
        "required": ["path"],
    },
)
def workspace_delete(path: str) -> str:
    p = _resolve(path)
    if not _safe(p):
        return "Path outside workspace."
    if not p.exists():
        return f"Not found: {path}"
    try:
        if p.is_file():
            p.unlink()
            return f"Deleted file: {path}"
        p.rmdir()
        return f"Deleted folder: {path}"
    except OSError as e:
        return f"Error: {e}"


@tool(
    name="workspace_move",
    description=(
        "Move or rename a file/folder within the workspace. "
        "Use to reorganize files into subfolders."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "src": {"type": "string", "description": "Source path"},
            "dst": {"type": "string", "description": "Destination path or folder"},
        },
        "required": ["src", "dst"],
    },
)
def workspace_move(src: str, dst: str) -> str:
    from pathlib import Path
    s = _resolve(src)
    d = _resolve(dst)
    if not _safe(s) or not _safe(d):
        return "Paths must stay inside workspace."
    if not s.exists():
        return f"Source not found: {src}"
    if d.is_dir():
        d = d / s.name
    try:
        d.parent.mkdir(parents=True, exist_ok=True)
        s.rename(d)
        return f"Moved: {src} → {d.relative_to(_ws())}"
    except Exception as e:
        return f"Error: {e}"


@tool(
    name="workspace_mkdir",
    description="Create a subfolder in the workspace.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Folder path to create"},
        },
        "required": ["path"],
    },
)
def workspace_mkdir(path: str) -> str:
    p = _resolve(path)
    if not _safe(p):
        return "Path outside workspace."
    try:
        p.mkdir(parents=True, exist_ok=True)
        return f"Created: {p.relative_to(_ws())}"
    except Exception as e:
        return f"Error: {e}"


@tool(
    name="copy_file",
    description=(
        "Copy a file to a new location within the workspace. "
        "Use to duplicate a template or create a new file based on an existing one."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "src": {"type": "string", "description": "Source file path"},
            "dst": {"type": "string", "description": "Destination path (file or folder)"},
        },
        "required": ["src", "dst"],
    },
)
def copy_file(src: str, dst: str) -> str:
    import shutil
    from pathlib import Path
    s = _resolve(src)
    d = _resolve(dst)
    if not _safe(s) or not _safe(d):
        return "Paths must stay inside workspace."
    if not s.exists():
        return f"Source not found: {src}"
    if not s.is_file():
        return f"Source is not a file: {src}"
    if d.is_dir():
        d = d / s.name
    try:
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
        return f"Copied: {s.relative_to(_ws())} → {d.relative_to(_ws())}"
    except Exception as e:
        return f"Error: {e}"
