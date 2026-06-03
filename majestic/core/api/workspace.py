"""Desktop API — workspace files: list output tree, read, delete."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from ._auth import require_token

router = APIRouter(prefix="/workspace", tags=["workspace"])

_PROFILES_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "profiles"

_TEXT_SUFFIXES = {
    ".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".py", ".js", ".ts", ".html",
}


def _output_dir(profile: str) -> Path:
    d = _PROFILES_ROOT / profile
    if not d.exists():
        raise HTTPException(status_code=404, detail=f"Profile '{profile}' not found")
    out = d / "workspace" / "output"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _safe_path(base: Path, rel: str) -> Path:
    """Resolve rel against base and verify it stays inside base (path traversal guard)."""
    target = (base / rel).resolve()
    if not str(target).startswith(str(base.resolve())):
        raise HTTPException(status_code=400, detail="Invalid path")
    return target


@router.get("/{profile}/files")
async def list_files(profile: str, _: None = Depends(require_token)) -> dict:
    out = _output_dir(profile)
    files = []
    for f in sorted(out.rglob("*")):
        if f.is_file():
            rel = f.relative_to(out).as_posix()
            files.append(
                {
                    "path": rel,
                    "name": f.name,
                    "size": f.stat().st_size,
                    "modified": f.stat().st_mtime,
                    "type": f.suffix.lstrip(".") or "file",
                }
            )
    return {"files": files}


@router.get("/{profile}/file")
async def read_file(
    profile: str,
    path: str = Query(..., description="Relative path inside output/"),
    _: None = Depends(require_token),
) -> dict:
    out = _output_dir(profile)
    target = _safe_path(out, path)

    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if target.suffix in _TEXT_SUFFIXES:
        content = target.read_text(encoding="utf-8", errors="replace")
        return {"path": path, "content": content, "binary": False}

    # Binary files: return base64
    import base64

    content_b64 = base64.b64encode(target.read_bytes()).decode()
    return {"path": path, "content": content_b64, "binary": True}


@router.delete("/{profile}/file")
async def delete_file(
    profile: str,
    path: str = Query(..., description="Relative path inside output/"),
    _: None = Depends(require_token),
) -> dict:
    out = _output_dir(profile)
    target = _safe_path(out, path)

    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")

    target.unlink()
    return {"status": "deleted", "path": path}
