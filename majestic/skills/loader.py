"""
Skills stored as Markdown files in MAJESTIC_HOME/skills/*.md.

Each file has YAML frontmatter (name, description, tags, usage_count, created)
followed by a Markdown body with goal, steps, and examples.
"""
import re
import yaml
from datetime import datetime
from pathlib import Path
from typing import Optional

from majestic.constants import SKILLS_DIR


def list_skills() -> list[dict]:
    """Return metadata for all skills (without body)."""
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    skills = []
    for path in sorted(SKILLS_DIR.glob("*.md")):
        meta = _read_meta(path)
        skills.append(meta)
    return skills


def load_skill(name: str) -> Optional[dict]:
    """Load skill by name. Returns {meta, body} or None."""
    path = _path_for(name)
    if not path.exists():
        return None
    return _read_full(path)


def save_skill(
    name: str,
    description: str,
    body: str,
    tags: Optional[list[str]] = None,
) -> Path:
    """Create a new skill file. Returns its path."""
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "name":        name,
        "description": description,
        "tags":        tags or [],
        "usage_count": 0,
        "created":     datetime.now().strftime("%Y-%m-%d"),
    }
    path = _path_for(name)
    _write(path, meta, body)
    return path


def increment_usage(name: str) -> int:
    """Increment usage_count and update last_used. Returns new count."""
    path = _path_for(name)
    if not path.exists():
        return 0
    skill = _read_full(path)
    meta = skill["meta"]
    count = meta.get("usage_count", 0) + 1
    meta["usage_count"] = count
    meta["last_used"] = datetime.now().strftime("%Y-%m-%d")
    _write(path, meta, skill["body"])
    return count


def update_body(name: str, new_body: str) -> None:
    """Replace skill body (e.g. after LLM improvement)."""
    path = _path_for(name)
    if not path.exists():
        return
    skill = _read_full(path)
    _write(path, skill["meta"], new_body)


def delete_skill(name: str) -> bool:
    path = _path_for(name)
    if path.exists():
        path.unlink()
        return True
    return False


# ── Internals ─────────────────────────────────────────────────────────────────

def _path_for(name: str) -> Path:
    slug = re.sub(r"[^a-zA-Z0-9_\-]", "-", name.lower()).strip("-")
    return SKILLS_DIR / f"{slug}.md"


def _read_meta(path: Path) -> dict:
    meta, _ = _split_frontmatter(path.read_text(encoding="utf-8"))
    meta.setdefault("name", path.stem)
    return meta


def _read_full(path: Path) -> dict:
    meta, body = _split_frontmatter(path.read_text(encoding="utf-8"))
    meta.setdefault("name", path.stem)
    return {"meta": meta, "body": body.strip()}


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                return yaml.safe_load(parts[1]) or {}, parts[2]
            except Exception:
                pass
    return {}, text


def _write(path: Path, meta: dict, body: str) -> None:
    content = (
        f"---\n"
        f"{yaml.dump(meta, allow_unicode=True, default_flow_style=False)}"
        f"---\n\n"
        f"{body.strip()}\n"
    )
    path.write_text(content, encoding="utf-8")
