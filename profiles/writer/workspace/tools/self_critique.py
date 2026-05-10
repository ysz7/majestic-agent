"""
self_critique.py — Self-critique and refinement for Writer agent.

Usage:
    python self_critique.py '{"format":"linkedin","content":"...draft...","angle":"...","audience":"..."}' --env_file profiles/writer/.env
"""

import argparse
import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Env helpers (mirrored from write_content.py)
# ---------------------------------------------------------------------------

def _load_env(env_file: str = None) -> dict:
    env = {}
    candidates = []
    if env_file:
        candidates.append(Path(env_file))
    project_root = Path(__file__).parents[2]
    candidates.append(project_root / "profiles" / "writer" / ".env")
    candidates.append(project_root / ".env")

    for path in candidates:
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, _, v = line.partition("=")
                    env.setdefault(k.strip(), v.strip())
    return env


def _get_api_key(env: dict) -> str:
    key = env.get("OPENROUTER_API_KEY", "")
    if not key or key.startswith("sk-or-..."):
        return ""
    return key


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
PRIMARY_MODEL = "anthropic/claude-sonnet-4-5"
FALLBACK_MODELS = [
    "anthropic/claude-3-haiku",
    "meta-llama/llama-3.1-8b-instruct:free",
]


def _call_openrouter(api_key: str, messages: list, model: str) -> str:
    try:
        import httpx
    except ImportError:
        raise RuntimeError("httpx is not installed. Run: pip install httpx")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/majestic-agent",
        "X-Title": "Majestic Writer Agent — self_critique",
    }
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": 4096,
        "temperature": 0.3,
    }
    resp = httpx.post(OPENROUTER_URL, headers=headers, json=body, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _call_with_fallback(api_key: str, messages: list) -> str:
    models = [PRIMARY_MODEL] + FALLBACK_MODELS
    last_err = None
    for model in models:
        try:
            return _call_openrouter(api_key, messages, model)
        except Exception as exc:
            last_err = exc
            continue
    raise RuntimeError(f"All models failed. Last error: {last_err}")


# ---------------------------------------------------------------------------
# Critique prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a harsh, precise editor. You evaluate content with brutal honesty.\n"
    "You only accept scores of 8+ when the writing is genuinely excellent.\n"
    "You always return valid JSON and nothing else."
)

CRITIQUE_RESPONSE_SCHEMA = """{
  "scores": {
    "hook": <integer 1-10>,
    "specificity": <integer 1-10>,
    "human_voice": <integer 1-10>,
    "efficiency": <integer 1-10>,
    "conclusion": <integer 1-10>
  },
  "overall_score": <float>,
  "weak_sections": [{"section": "<name>", "issue": "<description>"}, ...],
  "refined_content": "<complete rewritten piece if overall < 7.5, else exact same content>",
  "changes_made": ["<change 1>", ...]
}"""


def _build_critique_prompt(fmt: str, content: str, angle: str, audience: str) -> str:
    return f"""You are a harsh editor reviewing this {fmt} piece.

Angle the piece should argue: {angle}
Target audience: {audience}

Content to review:
---
{content}
---

Evaluate:
1. Hook strength (1-10): does it stop scrolling/reading immediately?
2. Specificity (1-10): are claims backed by data/examples or just assertions?
3. Human voice (1-10): does it sound like a real person or AI?
4. Paragraph efficiency (1-10): does every paragraph earn its place?
5. Conclusion strength (1-10): does it give the reader something to do or think about?

For any score below 7, rewrite that section.

Return ONLY valid JSON matching this schema (no markdown, no explanation):
{CRITIQUE_RESPONSE_SCHEMA}

Rules:
- overall_score = average of the 5 scores
- If overall_score >= 7.5: set refined_content to the EXACT original content unchanged
- If overall_score < 7.5: set refined_content to a complete rewrite that fixes all weak sections
- changes_made: list what you changed (empty list if no changes)"""


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict:
    """Extract first JSON object from LLM response, stripping markdown fences."""
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove first and last fence lines
        inner = []
        in_block = False
        for line in lines:
            if line.startswith("```") and not in_block:
                in_block = True
                continue
            if line.startswith("```") and in_block:
                break
            if in_block:
                inner.append(line)
        text = "\n".join(inner)

    # Find first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in LLM response")
    return json.loads(text[start : end + 1])


# ---------------------------------------------------------------------------
# Offline fallback scores (when no API key)
# ---------------------------------------------------------------------------

def _offline_critique(content: str) -> dict:
    """Return a neutral critique without calling LLM."""
    word_count = len(content.split())
    # Give default scores — conservative 7.0 means no rewrite triggered
    return {
        "scores": {
            "hook": 7,
            "specificity": 7,
            "human_voice": 7,
            "efficiency": 7,
            "conclusion": 7,
        },
        "overall_score": 7.0,
        "weak_sections": [],
        "refined_content": content,
        "changes_made": [],
        "_note": "Offline fallback — no API key available, scores are defaults.",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def self_critique(payload: dict, env_file: str = None) -> dict:
    fmt = payload.get("format", "blog")
    content = payload.get("content", "")
    angle = payload.get("angle", "")
    audience = payload.get("audience", "")

    if not content.strip():
        return {"error": "No content provided to critique."}

    env = _load_env(env_file)
    api_key = _get_api_key(env)

    if not api_key:
        critique = _offline_critique(content)
        return {
            "final_content": content,
            "quality_score": critique["overall_score"],
            "critique": critique,
            "was_refined": False,
            "warning": "No OPENROUTER_API_KEY — offline fallback used.",
        }

    critique_prompt = _build_critique_prompt(fmt, content, angle, audience)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": critique_prompt},
    ]

    try:
        raw = _call_with_fallback(api_key, messages)
        critique = _extract_json(raw)
    except Exception as exc:
        # If LLM or JSON parsing fails, return original with warning
        return {
            "final_content": content,
            "quality_score": 0.0,
            "critique": {},
            "was_refined": False,
            "warning": f"Critique failed: {exc}. Returning original content.",
        }

    overall = float(critique.get("overall_score", 0.0))
    was_refined = overall < 7.5
    final_content = critique.get("refined_content", content) if was_refined else content

    # Ensure refined_content exists in critique for output
    critique.setdefault("refined_content", content)

    return {
        "final_content": final_content,
        "quality_score": overall,
        "critique": {
            "scores": critique.get("scores", {}),
            "overall_score": overall,
            "weak_sections": critique.get("weak_sections", []),
            "changes_made": critique.get("changes_made", []),
        },
        "was_refined": was_refined,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Self-critique and refinement loop for Writer agent."
    )
    parser.add_argument(
        "payload",
        help=(
            'JSON string with keys: format (required), content (required), '
            'angle, audience'
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

    required = ["format", "content"]
    missing = [k for k in required if k not in payload]
    if missing:
        print(json.dumps({"error": f"Missing required fields: {missing}"}))
        sys.exit(1)

    result = self_critique(payload, env_file=args.env_file)
    print(json.dumps(result, ensure_ascii=False))
