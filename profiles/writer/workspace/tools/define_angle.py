"""
define_angle.py — Angle and structure engine for Writer agent.

Usage:
    python define_angle.py '{"format":"linkedin","topic":"AI compliance","audience":"SaaS founders","research_data":{"key_facts":["..."]}}' --openrouter_key sk-or-...
    python define_angle.py '{"format":"blog","topic":"...","brief_id":1}' --env_file profiles/writer/.env
"""

import json
import sys
import argparse
import re
from pathlib import Path

try:
    import httpx
except ImportError:
    print(json.dumps({"error": "httpx is required: pip install httpx"}))
    sys.exit(1)

# ---------------------------------------------------------------------------
# Format structure templates
# ---------------------------------------------------------------------------

_STRUCTURES: dict = {
    "blog": {
        "hook": "Engaging opening that challenges assumptions or presents a surprising fact",
        "problem_context": "Establish why this matters to the reader",
        "main_argument_sections": 3,
        "evidence": "Data, examples, and expert opinions supporting the argument",
        "counterargument_section": "Address the strongest objection honestly",
        "conclusion_takeaway": "Clear actionable insight or call to action",
    },
    "linkedin": {
        "hook_line": "Single powerful line — curiosity gap or bold claim",
        "context": "2-3 sentences setting up the problem or insight",
        "body_paragraphs": 5,
        "takeaway": "The key lesson or insight distilled",
        "cta": "Soft call to action (comment, share, save)",
    },
    "twitter_thread": {
        "hook_tweet": "Tweet 1: bold claim or surprising stat that earns the follow",
        "evidence_tweets": 3,
        "how_why_tweets": 4,
        "example_tweets": 5,
        "summary_tweet": "Distilled insight",
        "cta_tweet": "Follow / retweet / bookmark ask",
    },
    "newsletter": {
        "story_opener": "Personal story or vivid scenario that creates connection",
        "insight": "The core idea or lesson drawn from the story",
        "practical_takeaway": "What the reader can do with this insight",
        "closing_note": "Personal sign-off that builds relationship",
    },
    "report": {
        "exec_summary": "Key findings and recommendations in 150 words",
        "background": "Context, scope, and methodology",
        "findings": 5,
        "analysis": "Interpretation of findings and patterns",
        "implications": "What these findings mean for the audience",
        "recommendations": "Prioritized action items",
        "sources": "Full citation list",
    },
    "landing_page": {
        "headline": "Primary value proposition — outcome-focused",
        "subheadline": "Expand on the promise",
        "pain_points": "3 bullets of reader's current frustrations",
        "solution": "How your offering solves each pain",
        "social_proof": "Testimonials or data points",
        "cta": "Clear, singular call to action",
    },
    "email_sequence": {
        "email_1_welcome": "Set expectations, deliver quick win",
        "email_2_problem": "Deepen the pain — you understand them",
        "email_3_solution": "Introduce the solution pathway",
        "email_4_proof": "Case study or social proof",
        "email_5_offer": "Clear CTA with urgency or reason to act now",
    },
    "script": {
        "hook": "First 5 seconds — pattern interrupt or bold question",
        "intro": "Who you are and why you're credible on this topic",
        "body_sections": 3,
        "examples": "Real-world illustrations of each point",
        "conclusion": "Summary + single action item",
        "outro": "Subscribe / like / follow ask",
    },
}

_DEFAULT_STRUCTURE: dict = {
    "intro": "Set context and thesis",
    "body_sections": 3,
    "conclusion": "Summary and call to action",
}

# ---------------------------------------------------------------------------
# Heuristic fallback angles (when no LLM key available)
# ---------------------------------------------------------------------------

_HEURISTIC_TEMPLATES: dict = {
    "blog": [
        "The conventional wisdom about {topic} is wrong — here's what the data actually shows.",
        "Most people approach {topic} backwards — starting with the wrong question entirely.",
        "{topic} is not a technology problem; it's a behavior problem disguised as one.",
    ],
    "linkedin": [
        "I was wrong about {topic} for 3 years — here's what changed my mind.",
        "The {topic} advice everyone gives is optimized for the giver, not the receiver.",
        "Nobody talks about the dark side of {topic} — but they should.",
    ],
    "twitter_thread": [
        "{topic} is broken, and most practitioners know it but won't say it publicly.",
        "The #1 mistake people make with {topic} (and how to avoid it):",
        "I studied 100 {topic} case studies. Here's what actually works:",
    ],
    "newsletter": [
        "What a failed attempt at {topic} taught me about what actually matters.",
        "The quiet shift happening in {topic} that most people haven't noticed yet.",
        "Why {topic} feels harder than it should be — and the fix nobody mentions.",
    ],
    "report": [
        "{topic} presents a structural challenge that current frameworks are not equipped to handle.",
        "The measurable impact of {topic} on outcomes is both larger and different than assumed.",
        "Current approaches to {topic} optimize for visibility over effectiveness.",
    ],
    "default": [
        "The prevailing approach to {topic} optimizes for the wrong outcome.",
        "{topic} requires a fundamentally different mental model than most practitioners use.",
        "The case for rethinking {topic} from first principles.",
    ],
}


def _heuristic_angles(topic: str, fmt: str) -> list[str]:
    templates = _HEURISTIC_TEMPLATES.get(fmt, _HEURISTIC_TEMPLATES["default"])
    return [t.format(topic=topic) for t in templates]


def _heuristic_result(topic: str, fmt: str) -> dict:
    angles = _heuristic_angles(topic, fmt)
    return {
        "topic": topic,
        "format": fmt,
        "angles_considered": angles,
        "selected_angle": angles[0],
        "why_strong": "This angle challenges the dominant assumption and creates a curiosity gap.",
        "supporting_points": [
            "Most practitioners operate on unexamined assumptions about this topic.",
            "Evidence from adjacent domains suggests the conventional approach is suboptimal.",
            "The audience's actual outcome differs from what the standard advice delivers.",
        ],
        "counterargument": "The conventional approach has worked well enough for most cases.",
        "rebuttal": "Worked well enough is not the same as optimal — and as complexity grows, good enough breaks down first.",
        "structure": _STRUCTURES.get(fmt, _DEFAULT_STRUCTURE),
        "source": "heuristic",
    }


# ---------------------------------------------------------------------------
# Env file parser
# ---------------------------------------------------------------------------

def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file and return key-value pairs."""
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            env[key] = val
    return env


def _resolve_api_key(openrouter_key: str | None, env_file: str | None) -> str | None:
    """
    Resolve OPENROUTER_API_KEY from (in priority order):
    1. --openrouter_key CLI arg
    2. --env_file path
    3. profiles/writer/.env (relative to this script's location)
    4. root .env (profiles/writer/workspace/tools/ → up 4 levels)
    """
    if openrouter_key:
        return openrouter_key

    # Candidate .env files
    candidates: list[Path] = []

    if env_file:
        candidates.append(Path(env_file))

    # profiles/writer/.env
    writer_env = Path(__file__).parents[2] / ".env"
    candidates.append(writer_env)

    # Root .env (repo root = parents[4] from tools/)
    root_env = Path(__file__).parents[4] / ".env"
    candidates.append(root_env)

    for candidate in candidates:
        env = _parse_env_file(candidate)
        key = env.get("OPENROUTER_API_KEY")
        if key:
            return key

    return None


# ---------------------------------------------------------------------------
# OpenRouter LLM call
# ---------------------------------------------------------------------------

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEFAULT_MODEL = "openai/gpt-4o-mini"


def _build_prompt(brief: dict) -> str:
    research_data = brief.get("research_data", {}) or {}
    key_facts = research_data.get("key_facts", [])
    sources = research_data.get("sources", [])

    research_summary = ""
    if key_facts:
        research_summary += "Key facts:\n" + "\n".join(f"- {f}" for f in key_facts[:5])
    if sources:
        source_urls = []
        for s in sources[:3]:
            if isinstance(s, str):
                source_urls.append(s)
            elif isinstance(s, dict):
                source_urls.append(s.get("url", str(s)))
        research_summary += "\nSources: " + ", ".join(source_urls)

    if not research_summary:
        research_summary = "No research data provided — rely on general knowledge."

    return f"""Given this content brief:
- Format: {brief.get("format", "blog")}
- Topic: {brief.get("topic", "")}
- Audience: {brief.get("audience", "general audience")}
- Tone: {brief.get("tone", "neutral")}
- Goal: {brief.get("goal", "inform")}
- Research data: {research_summary}

Generate 3 specific, arguable angles. Each angle must:
1. Be one clear sentence that takes a position (not just a topic)
2. Be counterintuitive or non-obvious
3. Be supportable with evidence

Then select the strongest angle and provide:
- selected_angle: the chosen angle sentence
- why_strong: 1 sentence explaining why
- supporting_points: 3 bullet points of evidence/reasoning
- counterargument: strongest objection
- rebuttal: how to address it
- angles_considered: list of all 3 angle sentences

Return ONLY valid JSON with these exact keys:
{{
  "angles_considered": ["angle1", "angle2", "angle3"],
  "selected_angle": "...",
  "why_strong": "...",
  "supporting_points": ["point1", "point2", "point3"],
  "counterargument": "...",
  "rebuttal": "..."
}}"""


def _call_llm(prompt: str, api_key: str) -> dict:
    """POST to OpenRouter and return parsed JSON from the LLM response."""
    payload = {
        "model": _DEFAULT_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert content strategist. "
                    "You always respond with valid JSON only — no markdown, no explanation outside the JSON object."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 800,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://majestic-agent",
        "X-Title": "Majestic Writer Agent",
    }

    with httpx.Client(timeout=30) as client:
        resp = client.post(_OPENROUTER_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    raw_content = data["choices"][0]["message"]["content"].strip()

    # Strip markdown code fences if present
    raw_content = re.sub(r"^```(?:json)?\s*", "", raw_content)
    raw_content = re.sub(r"\s*```$", "", raw_content).strip()

    return json.loads(raw_content)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def define_angle(
    payload_json: str,
    openrouter_key: str | None = None,
    env_file: str | None = None,
) -> dict:
    """
    Generate angle candidates, select the strongest, and return structure.

    payload_json: JSON string with keys: format, topic, audience (optional), research_data (optional)
    """
    try:
        brief = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON payload: {exc}") from exc

    if "topic" not in brief:
        raise ValueError("Missing required field: topic")
    if "format" not in brief:
        raise ValueError("Missing required field: format")

    topic = brief["topic"]
    fmt = brief["format"]
    structure = _STRUCTURES.get(fmt, _DEFAULT_STRUCTURE)

    # Attempt LLM-based angle generation
    api_key = _resolve_api_key(openrouter_key, env_file)

    if api_key:
        try:
            prompt = _build_prompt(brief)
            llm_result = _call_llm(prompt, api_key)
            return {
                "topic": topic,
                "format": fmt,
                "angles_considered": llm_result.get("angles_considered", []),
                "selected_angle": llm_result.get("selected_angle", ""),
                "why_strong": llm_result.get("why_strong", ""),
                "supporting_points": llm_result.get("supporting_points", []),
                "counterargument": llm_result.get("counterargument", ""),
                "rebuttal": llm_result.get("rebuttal", ""),
                "structure": structure,
                "source": "llm",
            }
        except Exception:
            # Fall through to heuristic on any LLM failure
            pass

    # Heuristic fallback (no API key or LLM failed)
    result = _heuristic_result(topic, fmt)
    result["structure"] = structure
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Angle and structure engine for Writer agent."
    )
    parser.add_argument(
        "payload",
        help="JSON string with keys: format (required), topic (required), audience, research_data.",
    )
    parser.add_argument(
        "--openrouter_key",
        type=str,
        default=None,
        help="OpenRouter API key (overrides .env files).",
    )
    parser.add_argument(
        "--env_file",
        type=str,
        default=None,
        help="Path to .env file containing OPENROUTER_API_KEY.",
    )
    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    try:
        result = define_angle(
            payload_json=args.payload,
            openrouter_key=args.openrouter_key,
            env_file=args.env_file,
        )
        print(json.dumps(result, indent=2))

    except ValueError as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
    except Exception as exc:
        print(json.dumps({"error": f"Unexpected error: {exc}"}))
        sys.exit(1)
