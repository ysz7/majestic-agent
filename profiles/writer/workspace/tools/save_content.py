"""
save_content.py — Save content to output directory and record in content.db.

Usage:
    python save_content.py save '{"format":"blog","title":"AI Compliance Is the Only SaaS Niche...","topic":"AI compliance","audience":"SaaS founders","angle":"...","content":"# Title\n\nBody...","word_count":1200,"quality_score":7.5,"sources":["https://..."]}'
    python save_content.py get_path "blog" "AI Compliance post"
"""

import json
import sys
import argparse
import re
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

# Path(__file__).parents[2] == profiles/writer/  (save_content.py → tools/ → workspace/ → writer/)
_WRITER_ROOT = Path(__file__).parents[2]
_TOOLS_DIR = Path(__file__).parent
_DB_CONTENT = _TOOLS_DIR / "db_content.py"


# ---------------------------------------------------------------------------
# Slug builder
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """Convert a title or topic string into a URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    return text[:60].strip("-")


# ---------------------------------------------------------------------------
# Format → output path resolver
# ---------------------------------------------------------------------------

def _resolve_output_path(fmt: str, slug: str, today: str) -> Path:
    """
    Return the absolute output Path for a given format and slug.

    For email_sequence: returns a directory path (not a file).
    For all others: returns a .md file path.
    """
    base = _WRITER_ROOT / "workspace" / "output"

    mapping = {
        "blog": base / "blog" / f"{today}-{slug}.md",
        "newsletter": base / "newsletter" / f"{today}-{slug}.md",
        "linkedin": base / "social" / "linkedin" / f"{today}-{slug}.md",
        "twitter_thread": base / "social" / "twitter" / f"{today}-{slug}.md",
        "email_sequence": base / "email" / slug,          # directory
        "landing_page": base / "landing" / f"{slug}.md",
        "report": base / "reports" / f"{today}-{slug}.md",
        "script": base / "drafts" / f"{today}-{slug}.md",
    }

    return mapping.get(fmt, base / "drafts" / f"{today}-{slug}.md")


# ---------------------------------------------------------------------------
# Frontmatter builder
# ---------------------------------------------------------------------------

def _build_frontmatter(meta: dict) -> str:
    """Build YAML frontmatter block from metadata dict."""
    lines = ["---"]
    lines.append(f'title: "{_escape_yaml(str(meta.get("title", "")))}"')
    lines.append(f'format: {meta.get("format", "")}')
    lines.append(f'topic: "{_escape_yaml(str(meta.get("topic", "")))}"')
    lines.append(f'audience: "{_escape_yaml(str(meta.get("audience", "")))}"')
    lines.append(f'angle: "{_escape_yaml(str(meta.get("angle", "")))}"')
    lines.append(f'word_count: {meta.get("word_count", 0)}')
    lines.append(f'quality_score: {meta.get("quality_score", 0.0)}')
    lines.append(f'created_at: {meta.get("created_at", datetime.now(timezone.utc).isoformat())}')

    sources = meta.get("sources", [])
    if sources:
        lines.append("sources:")
        for src in sources:
            lines.append(f"  - {src}")
    else:
        lines.append("sources: []")

    lines.append("---")
    return "\n".join(lines)


def _escape_yaml(text: str) -> str:
    """Minimal escaping for YAML inline double-quoted strings."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


# ---------------------------------------------------------------------------
# DB persistence
# ---------------------------------------------------------------------------

def _save_to_db(
    fmt: str,
    title: str,
    topic: str,
    audience: str,
    angle: str,
    word_count: int,
    file_path: str,
    sources: list,
    quality_score: float,
) -> dict:
    """Call db_content.py save and return {"id": N, "saved": bool}."""
    if not _DB_CONTENT.exists():
        return {"id": None, "saved": False, "reason": "db_content.py not found"}

    source_data = json.dumps({"sources": sources})
    payload = {
        "format": fmt,
        "title": title,
        "topic": topic,
        "audience": audience,
        "angle": angle,
        "word_count": word_count,
        "file_path": file_path,
        "source_data": source_data,
        "quality_score": quality_score,
    }

    try:
        result = subprocess.run(
            [sys.executable, str(_DB_CONTENT), "save", json.dumps(payload)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout.strip())
    except Exception:
        pass

    return {"id": None, "saved": False}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_path(fmt: str, title_hint: str) -> str:
    """Return the file path that would be used without actually saving."""
    today = date.today().isoformat()
    slug = _slugify(title_hint)
    path = _resolve_output_path(fmt, slug, today)
    return str(path)


def save(payload_json: str) -> dict:
    """
    Save written content to disk and record in content.db.

    Required payload keys: format, content
    Optional: title, topic, audience, angle, word_count, quality_score, sources
    """
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON payload: {exc}") from exc

    if "format" not in payload:
        raise ValueError("Missing required field: format")
    if "content" not in payload:
        raise ValueError("Missing required field: content")

    fmt = payload["format"]
    content: str = payload["content"]
    title: str = payload.get("title", "")
    topic: str = payload.get("topic", "")
    audience: str = payload.get("audience", "")
    angle: str = payload.get("angle", "")
    word_count: int = int(payload.get("word_count", len(content.split())))
    quality_score: float = float(payload.get("quality_score", 0.0))
    sources: list = payload.get("sources", [])

    today = date.today().isoformat()
    created_at = datetime.now(timezone.utc).isoformat()

    # Use title for slug; fall back to topic
    slug_source = title or topic or fmt
    slug = _slugify(slug_source)
    output_path = _resolve_output_path(fmt, slug, today)

    # email_sequence gets a directory — write an index.md inside it
    is_email_dir = fmt == "email_sequence"
    if is_email_dir:
        file_path = output_path / "index.md"
    else:
        file_path = output_path

    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Build full file content with frontmatter
    meta = {
        "title": title,
        "format": fmt,
        "topic": topic,
        "audience": audience,
        "angle": angle,
        "word_count": word_count,
        "quality_score": quality_score,
        "created_at": created_at,
        "sources": sources,
    }
    frontmatter = _build_frontmatter(meta)
    full_content = frontmatter + "\n\n" + content

    file_path.write_text(full_content, encoding="utf-8")

    # Record in DB
    db_result = _save_to_db(
        fmt=fmt,
        title=title,
        topic=topic,
        audience=audience,
        angle=angle,
        word_count=word_count,
        file_path=str(file_path),
        sources=sources,
        quality_score=quality_score,
    )

    return {
        "saved": True,
        "file_path": str(file_path),
        "content_id": db_result.get("id"),
        "format": fmt,
        "word_count": word_count,
        "quality_score": quality_score,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Save content to output directory and record in content.db."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # save
    p_save = sub.add_parser("save", help="Save content and record in DB.")
    p_save.add_argument(
        "payload",
        help=(
            "JSON string. Required keys: format, content. "
            "Optional: title, topic, audience, angle, word_count, quality_score, sources."
        ),
    )

    # get_path
    p_path = sub.add_parser("get_path", help="Return output file path without saving.")
    p_path.add_argument("format", help="Content format (e.g. blog, linkedin).")
    p_path.add_argument("title_hint", help="Title or topic string for slug generation.")

    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    try:
        if args.command == "save":
            result = save(args.payload)
            print(json.dumps(result, indent=2))

        elif args.command == "get_path":
            path = get_path(args.format, args.title_hint)
            print(json.dumps({"file_path": path}))

        else:
            parser.print_help()
            sys.exit(1)

    except ValueError as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
    except Exception as exc:
        print(json.dumps({"error": f"Unexpected error: {exc}"}))
        sys.exit(1)
