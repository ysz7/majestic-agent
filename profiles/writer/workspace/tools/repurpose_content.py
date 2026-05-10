"""
repurpose_content.py — Content repurposing engine.

Usage:
    python repurpose_content.py '{"source_file":"profiles/writer/workspace/output/blog/2026-05-10-ai-compliance.md","target_formats":["linkedin","twitter_thread"]}' --env_file profiles/writer/.env
    python repurpose_content.py '{"source_content":"...text...","target_formats":["linkedin"]}' --env_file profiles/writer/.env
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Tool paths
# ---------------------------------------------------------------------------

TOOLS_DIR = Path(__file__).parent
WRITE_CONTENT = TOOLS_DIR / "write_content.py"
SELF_CRITIQUE = TOOLS_DIR / "self_critique.py"
DB_CONTENT = TOOLS_DIR / "db_content.py"

PROJECT_ROOT = Path(__file__).parents[2]
OUTPUT_DIR = PROJECT_ROOT / "profiles" / "writer" / "workspace" / "output"


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------

def _run_tool(tool_path: Path, args: list) -> dict:
    """Run a sibling tool via subprocess and parse its JSON stdout."""
    cmd = [sys.executable, str(tool_path)] + args
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    stdout = result.stdout.strip()
    if not stdout:
        stderr = result.stderr.strip()
        return {"error": f"Tool returned no output. stderr: {stderr}"}
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {"error": f"Tool returned non-JSON output: {stdout[:200]}"}


# ---------------------------------------------------------------------------
# Source content loading
# ---------------------------------------------------------------------------

def _load_source(payload: dict) -> tuple[str, str]:
    """Return (content_text, source_format). source_format is inferred from file ext."""
    source_file = payload.get("source_file")
    source_content = payload.get("source_content")

    if source_content:
        return source_content, "text"

    if source_file:
        path = Path(source_file)
        if not path.is_absolute():
            # Try relative to project root
            path = PROJECT_ROOT / source_file
        if not path.exists():
            raise FileNotFoundError(f"Source file not found: {path}")
        text = path.read_text(encoding="utf-8")
        # Infer format from parent directory name
        fmt = path.parent.name if path.parent.name else "text"
        return text, fmt

    raise ValueError("Provide either 'source_file' or 'source_content' in payload.")


# ---------------------------------------------------------------------------
# Core insight extractor
# ---------------------------------------------------------------------------

def _extract_core_insight(content: str) -> dict:
    """
    Extract core argument, key points, and conclusion from source content.
    Simple heuristic — no LLM call needed here.
    """
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    # Title / core argument: first non-empty line (often a header)
    core_argument = lines[0].lstrip("#").strip() if lines else ""

    # Key points: lines starting with - or * or numbered (up to 5)
    key_points = []
    for line in lines:
        if line.startswith(("- ", "* ", "• ")) or (len(line) > 2 and line[0].isdigit() and line[1] in ".):"):
            point = line.lstrip("-*•0123456789.)").strip()
            if len(point) > 20:
                key_points.append(point)
        if len(key_points) >= 5:
            break

    # Conclusion: last substantive paragraph (> 50 chars, not a header)
    conclusion = ""
    for line in reversed(lines):
        if not line.startswith("#") and len(line) > 50:
            conclusion = line
            break

    return {
        "core_argument": core_argument,
        "key_points": key_points,
        "conclusion": conclusion,
    }


# ---------------------------------------------------------------------------
# Output file saver
# ---------------------------------------------------------------------------

def _save_to_file(content: str, fmt: str) -> str:
    """Save content to output/<format>/<date>-repurposed.md and return path."""
    out_dir = OUTPUT_DIR / fmt
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Find a non-colliding filename
    base = f"{date_str}-repurposed"
    candidate = out_dir / f"{base}.md"
    counter = 1
    while candidate.exists():
        candidate = out_dir / f"{base}-{counter}.md"
        counter += 1
    candidate.write_text(content, encoding="utf-8")
    return str(candidate)


# ---------------------------------------------------------------------------
# DB saver
# ---------------------------------------------------------------------------

def _save_to_db(fmt: str, file_path: str, word_count: int, quality_score: float,
                angle: str, topic: str, audience: str) -> int:
    """Save content record to db_content.py and return content_id."""
    db_payload = json.dumps({
        "format": fmt,
        "title": f"Repurposed — {fmt}",
        "topic": topic,
        "audience": audience,
        "angle": angle,
        "word_count": word_count,
        "file_path": file_path,
        "source_data": "{}",
        "quality_score": quality_score,
    })
    result = _run_tool(DB_CONTENT, ["save", db_payload])
    return result.get("id", 0)


# ---------------------------------------------------------------------------
# Repurpose one format
# ---------------------------------------------------------------------------

def _repurpose_one(
    source_content: str,
    source_format: str,
    target_format: str,
    core_insight: dict,
    env_file: str = None,
) -> dict:
    """Repurpose source to one target format. Returns result dict."""
    angle = core_insight.get("core_argument", "")
    key_points = core_insight.get("key_points", [])

    # Build the repurpose prompt by embedding source then adding format instructions
    repurpose_prefix = (
        f"I have this {source_format} content:\n\n"
        f"{source_content}\n\n"
        f"Repurpose this as a {target_format}.\n"
        f"IMPORTANT: Do not copy-paste. Adapt the core argument natively to {target_format}.\n"
        f"Apply {target_format} structure and conventions.\n"
        f"Extract and reframe the key insight — don't summarize, reimagine.\n\n"
    )

    # The brief for write_content — we inject the repurpose_prefix via the angle field
    brief = {
        "format": target_format,
        "topic": angle[:120] if angle else "repurposed content",
        "audience": "",
        "angle": angle,
        "key_points": key_points,
        "sources": [],
        "avoid": [],
        "research_data": {"repurpose_context": repurpose_prefix},
        "style_guide": [],
        "_repurpose_prefix": repurpose_prefix,
    }

    # Build custom payload: we want the repurpose context injected into the user prompt.
    # We do this by adding a special key that write_content can use — but since write_content
    # doesn't natively handle this, we call it with format=repurpose and pass the full
    # source inline via research_data. write_content will include research_data in its prompt.
    brief["research_data"] = {
        "original_content": source_content,
        "repurpose_instruction": (
            f"Repurpose the above {source_format} content as {target_format}. "
            "Do not copy-paste — adapt the core argument natively. "
            f"Apply {target_format} structure and conventions."
        ),
    }

    wc_args = [json.dumps(brief)]
    if env_file:
        wc_args += ["--env_file", env_file]

    write_result = _run_tool(WRITE_CONTENT, wc_args)

    if "error" in write_result:
        return {"format": target_format, "error": write_result["error"]}

    draft = write_result.get("content", "")
    word_count = write_result.get("word_count", len(draft.split()))

    # Self-critique
    critique_payload = json.dumps({
        "format": target_format,
        "content": draft,
        "angle": angle,
        "audience": "",
    })
    critique_args = [critique_payload]
    if env_file:
        critique_args += ["--env_file", env_file]

    critique_result = _run_tool(SELF_CRITIQUE, critique_args)
    final_content = critique_result.get("final_content", draft)
    quality_score = critique_result.get("quality_score", 0.0)
    word_count = len(final_content.split())

    # Save to file
    file_path = _save_to_file(final_content, target_format)

    # Save to DB
    content_id = _save_to_db(
        fmt=target_format,
        file_path=file_path,
        word_count=word_count,
        quality_score=quality_score,
        angle=angle,
        topic=brief.get("topic", ""),
        audience="",
    )

    return {
        "format": target_format,
        "file_path": file_path,
        "content_id": content_id,
        "word_count": word_count,
        "quality_score": quality_score,
        "was_refined": critique_result.get("was_refined", False),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def repurpose_content(payload: dict, env_file: str = None) -> dict:
    target_formats = payload.get("target_formats", [])
    if not target_formats:
        return {"error": "No target_formats specified."}

    try:
        source_content, source_format = _load_source(payload)
    except (FileNotFoundError, ValueError) as exc:
        return {"error": str(exc)}

    if not source_content.strip():
        return {"error": "Source content is empty."}

    core_insight = _extract_core_insight(source_content)

    results = []
    for fmt in target_formats:
        result = _repurpose_one(
            source_content=source_content,
            source_format=source_format,
            target_format=fmt,
            core_insight=core_insight,
            env_file=env_file,
        )
        results.append(result)

    return {"repurposed": results}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Content repurposing engine for Writer agent."
    )
    parser.add_argument(
        "payload",
        help=(
            'JSON string with keys: target_formats (required, list), '
            'source_file (path) OR source_content (string)'
        ),
    )
    parser.add_argument(
        "--env_file",
        default=None,
        help="Path to .env file with OPENROUTER_API_KEY (default: auto-detect).",
    )
    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    try:
        payload = json.loads(args.payload)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"Invalid JSON payload: {exc}"}))
        sys.exit(1)

    if "target_formats" not in payload:
        print(json.dumps({"error": "Missing required field: target_formats"}))
        sys.exit(1)

    if "source_file" not in payload and "source_content" not in payload:
        print(json.dumps({"error": "Provide 'source_file' or 'source_content' in payload."}))
        sys.exit(1)

    result = repurpose_content(payload, env_file=args.env_file)
    print(json.dumps(result, ensure_ascii=False))
