"""
write_content.py — Main writing engine for Writer agent.

Usage:
    python write_content.py '{"brief_id":1,"format":"blog","topic":"AI compliance","audience":"SaaS founders","angle":"AI compliance is the only SaaS niche created by regulation","structure":{"hook":"..."},"research_data":{"key_facts":["..."]},"style_guide":[]}' --env_file profiles/writer/.env
"""

import argparse
import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------

def _load_env(env_file: str = None) -> dict:
    """Load key=value pairs from env_file (skips comments/blank lines)."""
    env = {}
    candidates = []
    if env_file:
        candidates.append(Path(env_file))
    # profiles/writer/.env relative to project root
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
# Format prompt builder
# ---------------------------------------------------------------------------

def _build_user_prompt(brief: dict) -> str:
    fmt = brief.get("format", "blog")
    topic = brief.get("topic", "")
    audience = brief.get("audience", "")
    angle = brief.get("angle", "")
    research = brief.get("research_data", {})
    style_guide = brief.get("style_guide", [])
    structure = brief.get("structure", {})

    key_points = brief.get("key_points", [])
    if not key_points and isinstance(research, dict):
        key_points = research.get("key_facts", [])

    sources = brief.get("sources", [])
    if not sources and isinstance(research, dict):
        sources = research.get("sources", [])

    avoid = brief.get("avoid", [])
    goal = brief.get("goal", "")

    # Serialize helpers
    key_points_str = "\n".join(f"- {p}" for p in key_points) if key_points else "(none provided)"
    sources_str = "\n".join(f"- {s}" for s in sources) if sources else "(none provided)"
    avoid_str = "\n".join(f"- {a}" for a in avoid) if avoid else "(none)"
    style_str = "\n".join(f"- {r}" for r in style_guide) if style_guide else "(none)"
    research_str = json.dumps(research, indent=2) if research else "(none)"

    if fmt == "blog":
        return f"""Write a blog post following this brief:
- Audience: {audience}
- Angle (your main argument): {angle}
- Key points to include:
{key_points_str}
- Sources to cite:
{sources_str}
- Avoid: {avoid_str}
- Structure: Hook → Problem/context → Main argument (3 sections) → Evidence → Counterargument address → Conclusion + takeaway
- Length: 800-2500 words
- Style guide rules:
{style_str}

Research data available:
{research_str}

Write the complete blog post in Markdown. Use ## for section headers."""

    elif fmt == "linkedin":
        kp0 = key_points[0] if key_points else angle
        return f"""Write a LinkedIn post following this brief:
- Audience: {audience}
- Angle (your opening claim): {angle}
- Key insight: {kp0}
- Avoid: {avoid_str}
- Structure: Hook line (stop-scroll) → Context (1-2 lines) → Body (3-5 short paragraphs, line breaks) → Takeaway → Question or CTA
- Length: 150-300 words
- NO hashtags unless requested
- Style guide:
{style_str}"""

    elif fmt == "twitter_thread":
        return f"""Write a Twitter/X thread following this brief:
- Angle (tweet 1 claim): {angle}
- Evidence:
{key_points_str}
- Structure: Tweet 1 (hook) → Tweets 2-4 (evidence) → Tweets 5-8 (how/why) → Tweets 9-12 (examples) → Tweet 13 (summary) → Tweet 14 (CTA)
- Each tweet must be standalone and under 280 characters
- Number each tweet: "1/ The claim..." "2/ Evidence shows..."
- Style guide:
{style_str}"""

    elif fmt == "newsletter":
        return f"""Write a newsletter issue:
- Audience: {audience}
- Core insight: {angle}
- Tone: personal, narrative, first-person
- Structure: Story opener (2-3 sentences) → Main insight → Practical takeaway → Closing thought
- Length: 400-800 words
- Must feel like a real person wrote it, not AI
- Style guide:
{style_str}"""

    elif fmt == "report":
        return f"""Write an analytical report:
- Audience: {audience}
- Central finding: {angle}
- Sections: Executive Summary → Background → Key Findings (3-5 numbered sections) → Analysis → Implications → Recommendations → Sources
- Cite all claims with source URLs
- Length: 1500-3000 words
- Format: Markdown with ## headers
- Key points:
{key_points_str}
- Sources:
{sources_str}"""

    elif fmt == "email_sequence":
        return f"""Write a 5-email sequence:
- Product/topic: {topic}
- Audience: {audience}
- Goal: {goal}
- Arc: Email 1 (acknowledge problem) → Email 2 (why existing solutions fail) → Email 3 (new approach/insight) → Email 4 (social proof) → Email 5 (offer/CTA)
- Each email: Subject line + Preview text + Body (100-200 words)
- Conversational tone, specific examples

Return as JSON: {{"emails": [{{"subject":"...","preview":"...","body":"..."}}, ...]}}"""

    elif fmt == "landing_page":
        return f"""Write landing page copy:
- Product: {topic}
- Audience: {audience}
- Core value prop: {angle}
- Sections: Hero headline + subheadline → Problem → Solution + 3 benefits → How it works (3 steps) → Social proof placeholders → FAQ (3 questions) → CTA
- Every line must earn its place. No filler.
- Style guide:
{style_str}"""

    elif fmt == "script":
        script_type = brief.get("script_type", "video")
        duration = brief.get("duration", 5)
        word_target = duration * 150
        return f"""Write a {script_type} script:
- Topic: {topic}
- Duration: {duration} minutes
- Audience: {audience}
- Hook (first 30 seconds): {angle}
- Write in natural speech — contractions, short sentences
- Mark pauses: [PAUSE], transitions: [TRANSITION], B-roll: [B-ROLL: description]
- Length: approximately {word_target} words
- Style guide:
{style_str}"""

    else:
        # Generic fallback
        return f"""Write a {fmt} piece:
- Topic: {topic}
- Audience: {audience}
- Angle: {angle}
- Key points:
{key_points_str}
- Length: 500-1500 words
- Style guide:
{style_str}

Research data:
{research_str}"""


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are an expert ghostwriter and content strategist.\n"
    "Your writing is specific, human, and never generic.\n"
    "You never use filler phrases like \"In today's fast-paced world\".\n"
    "Every sentence earns its place. You cite specific data and examples.\n"
    "You write for the exact audience defined in the brief.\n"
    "Follow the angle and structure provided exactly."
)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
PRIMARY_MODEL = "anthropic/claude-sonnet-4-5"
FALLBACK_MODELS = [
    "anthropic/claude-3-haiku",
    "meta-llama/llama-3.1-8b-instruct:free",
]


def _call_openrouter(api_key: str, user_prompt: str, model: str) -> str:
    """Call OpenRouter chat completions. Returns content string."""
    try:
        import httpx
    except ImportError:
        raise RuntimeError("httpx is not installed. Run: pip install httpx")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/majestic-agent",
        "X-Title": "Majestic Writer Agent",
    }
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 4096,
        "temperature": 0.7,
    }
    resp = httpx.post(OPENROUTER_URL, headers=headers, json=body, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"], data.get("model", model)


def _call_with_fallback(api_key: str, user_prompt: str) -> tuple[str, str]:
    """Try primary model then fallbacks. Returns (content, model_used)."""
    models = [PRIMARY_MODEL] + FALLBACK_MODELS
    last_err = None
    for model in models:
        try:
            content, model_used = _call_openrouter(api_key, user_prompt, model)
            return content, model_used
        except Exception as exc:
            last_err = exc
            continue
    raise RuntimeError(f"All models failed. Last error: {last_err}")


# ---------------------------------------------------------------------------
# Fallback template
# ---------------------------------------------------------------------------

def _fallback_template(brief: dict) -> str:
    fmt = brief.get("format", "content")
    topic = brief.get("topic", "[topic]")
    angle = brief.get("angle", "[angle]")
    audience = brief.get("audience", "[audience]")
    return f"""# {topic}

*[This is a placeholder — LLM call failed. Fill in manually.]*

## The Core Argument

{angle}

## For {audience}

[Section 1 — Context]

[Section 2 — Main evidence]

[Section 3 — Implications]

## Takeaway

[Conclusion placeholder]
"""


# ---------------------------------------------------------------------------
# Word count
# ---------------------------------------------------------------------------

def _count_words(text: str) -> int:
    return len(text.split())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def write_content(brief: dict, env_file: str = None) -> dict:
    env = _load_env(env_file)
    api_key = _get_api_key(env)
    fmt = brief.get("format", "blog")
    user_prompt = _build_user_prompt(brief)

    if not api_key:
        content = _fallback_template(brief)
        return {
            "content": content,
            "word_count": _count_words(content),
            "model_used": "none (no API key)",
            "format": fmt,
            "warning": "No OPENROUTER_API_KEY found. Returning placeholder template.",
        }

    try:
        content, model_used = _call_with_fallback(api_key, user_prompt)
    except Exception as exc:
        content = _fallback_template(brief)
        return {
            "content": content,
            "word_count": _count_words(content),
            "model_used": "none (LLM error)",
            "format": fmt,
            "warning": f"LLM call failed: {exc}. Returning placeholder template.",
        }

    return {
        "content": content,
        "word_count": _count_words(content),
        "model_used": model_used,
        "format": fmt,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Main writing engine for Writer agent. Produces content for any format using LLM."
    )
    parser.add_argument(
        "payload",
        help=(
            "JSON string with keys: format (required), topic, audience, angle, "
            "key_points, sources, avoid, research_data, style_guide, structure, "
            "goal, script_type, duration"
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
        brief = json.loads(args.payload)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"Invalid JSON payload: {exc}"}))
        sys.exit(1)

    if "format" not in brief:
        print(json.dumps({"error": "Missing required field: format"}))
        sys.exit(1)

    result = write_content(brief, env_file=args.env_file)
    print(json.dumps(result, ensure_ascii=False))
