"""Workspace browser API — list, read, write, delete files in WORKSPACE_DIR."""
from __future__ import annotations

import os
import base64
import mimetypes
from pathlib import Path
from datetime import datetime


def _safe_path(rel: str) -> Path | None:
    """Resolve rel path inside WORKSPACE_DIR; return None if path traversal detected."""
    from majestic.constants import WORKSPACE_DIR
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        resolved = (WORKSPACE_DIR / rel.lstrip("/")).resolve()
        resolved.relative_to(WORKSPACE_DIR.resolve())
        return resolved
    except (ValueError, Exception):
        return None


_TEXT_EXTS = {
    ".txt", ".md", ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml",
    ".toml", ".csv", ".sh", ".bash", ".html", ".css", ".sql", ".xml", ".ini",
    ".cfg", ".conf", ".log", ".rst", ".env",
}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico"}
_SIZE_LIMIT  = 1 * 1024 * 1024  # 1 MB — above this: download-only


def _file_type(p: Path) -> str:
    if p.is_dir():
        return "dir"
    ext = p.suffix.lower()
    if ext in _IMAGE_EXTS:
        return "image"
    if ext in _TEXT_EXTS:
        return "text"
    return "binary"


def handle_list(qs: str) -> dict:
    """GET /api/workspace/list?path=subdir"""
    from urllib.parse import parse_qs
    rel   = parse_qs(qs).get("path", [""])[0]
    dpath = _safe_path(rel)
    if dpath is None:
        return {"error": "invalid path"}
    if not dpath.exists():
        dpath.mkdir(parents=True, exist_ok=True)
    if not dpath.is_dir():
        return {"error": "not a directory"}

    items = []
    for entry in sorted(dpath.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        stat = entry.stat()
        items.append({
            "name":        entry.name,
            "path":        str(entry.relative_to(_safe_path("").parent if False else _root())),
            "type":        _file_type(entry),
            "size":        stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return {"items": items, "path": rel}


def _root() -> Path:
    from majestic.constants import WORKSPACE_DIR
    return WORKSPACE_DIR


def handle_read_file(qs: str) -> dict:
    """GET /api/workspace/file?path=..."""
    from urllib.parse import parse_qs
    rel   = parse_qs(qs).get("path", [""])[0]
    fpath = _safe_path(rel)
    if fpath is None or not fpath.exists() or fpath.is_dir():
        return {"error": "file not found"}

    ftype = _file_type(fpath)
    size  = fpath.stat().st_size

    if ftype == "image":
        raw = fpath.read_bytes()
        mime = mimetypes.guess_type(fpath.name)[0] or "application/octet-stream"
        return {"type": "image", "content_b64": base64.b64encode(raw).decode(), "mime": mime, "size": size}

    if ftype == "binary" or size > _SIZE_LIMIT:
        return {"type": "binary", "size": size, "name": fpath.name}

    try:
        content = fpath.read_text(encoding="utf-8", errors="replace")
        return {"type": "text", "content": content, "ext": fpath.suffix.lower(), "size": size}
    except Exception as e:
        return {"error": str(e)}


def handle_save_file(body: dict) -> dict:
    """POST /api/workspace/file  {path, content}"""
    rel     = body.get("path", "")
    content = body.get("content", "")
    if not rel:
        return {"error": "path required"}
    fpath = _safe_path(rel)
    if fpath is None:
        return {"error": "invalid path"}
    try:
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content, encoding="utf-8")
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


def handle_upload(body: dict) -> dict:
    """POST /api/workspace/upload  {path, content_b64, filename}"""
    rel      = body.get("path", "")
    filename = body.get("filename", "")
    b64      = body.get("content_b64", "")
    if not filename or not b64:
        return {"error": "filename and content_b64 required"}
    dest_dir = _safe_path(rel) if rel else _root()
    if dest_dir is None:
        return {"error": "invalid path"}
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = (dest_dir / filename).resolve()
    try:
        dest.relative_to(_root().resolve())
    except ValueError:
        return {"error": "invalid path"}
    try:
        dest.write_bytes(base64.b64decode(b64))
        return {"ok": True, "path": str(dest.relative_to(_root()))}
    except Exception as e:
        return {"error": str(e)}


def handle_delete(qs: str) -> dict:
    """DELETE /api/workspace/file?path=..."""
    from urllib.parse import parse_qs
    import shutil
    rel   = parse_qs(qs).get("path", [""])[0]
    fpath = _safe_path(rel)
    if fpath is None or not fpath.exists():
        return {"error": "not found"}
    try:
        if fpath.is_dir():
            shutil.rmtree(fpath)
        else:
            fpath.unlink()
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}


def handle_mkdir(body: dict) -> dict:
    """POST /api/workspace/mkdir  {path}"""
    rel   = body.get("path", "")
    if not rel:
        return {"error": "path required"}
    dpath = _safe_path(rel)
    if dpath is None:
        return {"error": "invalid path"}
    try:
        dpath.mkdir(parents=True, exist_ok=True)
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}
