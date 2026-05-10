"""
write_brief.py — Content brief builder for Writer agent.

Usage:
    # Scenario 1: direct user request
    python write_brief.py direct '{"format":"blog","topic":"AI compliance SaaS","audience":"SaaS founders","tone":"authoritative","goal":"build_authority"}'

    # Scenario 2: delegation from another agent
    python write_brief.py delegation '{"format":"blog","topic":"freelancer tax pain","delegation_source":"pain_hunter","research_data":{"pain_points":["..."],"sources":["https://..."],"validation_score":8.4,"target_audience":"US freelancers"}}'

    # Get brief template for a format
    python write_brief.py template blog
"""

import json
import sys
import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# db_briefs.py lives in the same tools/ directory
_TOOLS_DIR = Path(__file__).parent
_DB_BRIEFS = _TOOLS_DIR / "db_briefs.py"

# ---------------------------------------------------------------------------
# Format-aware defaults
# ---------------------------------------------------------------------------

_FORMAT_DEFAULTS: dict = {
    "blog": {"tone": "authoritative", "goal": "build_authority", "audience": "general audience"},
    "linkedin": {"tone": "professional", "goal": "build_authority", "audience": "professionals"},
    "twitter_thread": {"tone": "conversational", "goal": "engagement", "audience": "general audience"},
    "newsletter": {"tone": "friendly", "goal": "nurture", "audience": "subscribers"},
    "report": {"tone": "analytical", "goal": "inform", "audience": "decision makers"},
    "landing_page": {"tone": "persuasive", "goal": "convert", "audience": "potential customers"},
    "email_sequence": {"tone": "direct", "goal": "convert", "audience": "leads"},
    "script": {"tone": "conversational", "goal": "engage", "audience": "viewers"},
}

_BRIEF_TEMPLATES: dict = {
    "blog": {
        "id": None,
        "format": "blog",
        "topic": "",
        "audience": "general audience",
        "angle": None,
        "tone": "authoritative",
        "goal": "build_authority",
        "key_points": [],
        "sources": [],
        "avoid": ["In today's fast-paced world", "generic openers"],
        "scenario": "direct",
        "delegation_source": None,
        "research_data": None,
        "needs_research": True,
    },
    "linkedin": {
        "id": None,
        "format": "linkedin",
        "topic": "",
        "audience": "professionals",
        "angle": None,
        "tone": "professional",
        "goal": "build_authority",
        "key_points": [],
        "sources": [],
        "avoid": ["In today's fast-paced world", "generic openers", "humbled to announce"],
        "scenario": "direct",
        "delegation_source": None,
        "research_data": None,
        "needs_research": True,
    },
    "twitter_thread": {
        "id": None,
        "format": "twitter_thread",
        "topic": "",
        "audience": "general audience",
        "angle": None,
        "tone": "conversational",
        "goal": "engagement",
        "key_points": [],
        "sources": [],
        "avoid": ["In today's fast-paced world", "long intros", "walls of text"],
        "scenario": "direct",
        "delegation_source": None,
        "research_data": None,
        "needs_research": True,
    },
    "newsletter": {
        "id": None,
        "format": "newsletter",
        "topic": "",
        "audience": "subscribers",
        "angle": None,
        "tone": "friendly",
        "goal": "nurture",
        "key_points": [],
        "sources": [],
        "avoid": ["In today's fast-paced world", "generic openers", "salesy language"],
        "scenario": "direct",
        "delegation_source": None,
        "research_data": None,
        "needs_research": True,
    },
    "report": {
        "id": None,
        "format": "report",
        "topic": "",
        "audience": "decision makers",
        "angle": None,
        "tone": "analytical",
        "goal": "inform",
        "key_points": [],
        "sources": [],
        "avoid": ["vague claims", "unsupported statistics"],
        "scenario": "direct",
        "delegation_source": None,
        "research_data": None,
        "needs_research": True,
    },
    "landing_page": {
        "id": None,
        "format": "landing_page",
        "topic": "",
        "audience": "potential customers",
        "angle": None,
        "tone": "persuasive",
        "goal": "convert",
        "key_points": [],
        "sources": [],
        "avoid": ["In today's fast-paced world", "jargon", "passive voice"],
        "scenario": "direct",
        "delegation_source": None,
        "research_data": None,
        "needs_research": True,
    },
    "email_sequence": {
        "id": None,
        "format": "email_sequence",
        "topic": "",
        "audience": "leads",
        "angle": None,
        "tone": "direct",
        "goal": "convert",
        "key_points": [],
        "sources": [],
        "avoid": ["In today's fast-paced world", "vague subject lines"],
        "scenario": "direct",
        "delegation_source": None,
        "research_data": None,
        "needs_research": True,
    },
    "script": {
        "id": None,
        "format": "script",
        "topic": "",
        "audience": "viewers",
        "angle": None,
        "tone": "conversational",
        "goal": "engage",
        "key_points": [],
        "sources": [],
        "avoid": ["In today's fast-paced world", "monotone delivery cues", "wall-of-text paragraphs"],
        "scenario": "direct",
        "delegation_source": None,
        "research_data": None,
        "needs_research": True,
    },
}

_DEFAULT_TEMPLATE: dict = {
    "id": None,
    "format": "",
    "topic": "",
    "audience": "general audience",
    "angle": None,
    "tone": "neutral",
    "goal": "inform",
    "key_points": [],
    "sources": [],
    "avoid": ["In today's fast-paced world", "generic openers"],
    "scenario": "direct",
    "delegation_source": None,
    "research_data": None,
    "needs_research": True,
}


# ---------------------------------------------------------------------------
# DB persistence (delegates to db_briefs.py via subprocess)
# ---------------------------------------------------------------------------

def _save_to_db(brief: dict) -> dict:
    """Call db_briefs.py save and return the saved record (with id)."""
    if not _DB_BRIEFS.exists():
        # db_briefs.py not present — return brief as-is without id assignment
        return brief

    payload = json.dumps(brief)
    try:
        result = subprocess.run(
            [sys.executable, str(_DB_BRIEFS), "save", payload],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            saved = json.loads(result.stdout.strip())
            if isinstance(saved, dict) and "id" in saved:
                brief["id"] = saved["id"]
    except Exception:
        pass  # best-effort — don't fail the brief build if DB is unavailable

    return brief


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_template(format_name: str) -> dict:
    """Return a brief template dict with all required fields for that format."""
    template = _BRIEF_TEMPLATES.get(format_name, _DEFAULT_TEMPLATE.copy())
    # Return a fresh copy so callers can mutate freely
    result = dict(template)
    result["format"] = format_name
    return result


def build_direct(payload_json: str) -> dict:
    """
    Build a content brief from a direct user request.

    Required payload keys: format, topic
    Optional: audience, tone, goal, key_points, sources, angle, avoid
    """
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON payload: {exc}") from exc

    if "format" not in payload:
        raise ValueError("Missing required field: format")
    if "topic" not in payload:
        raise ValueError("Missing required field: topic")

    fmt = payload["format"]
    defaults = _FORMAT_DEFAULTS.get(fmt, {"tone": "neutral", "goal": "inform", "audience": "general audience"})

    sources = payload.get("sources", [])
    research_data = payload.get("research_data", None)
    needs_research = (not sources) and (research_data is None)

    brief: dict = {
        "id": None,
        "format": fmt,
        "topic": payload["topic"],
        "audience": payload.get("audience", defaults["audience"]),
        "angle": payload.get("angle", None),
        "tone": payload.get("tone", defaults["tone"]),
        "goal": payload.get("goal", defaults["goal"]),
        "key_points": payload.get("key_points", []),
        "sources": sources,
        "avoid": payload.get("avoid", ["In today's fast-paced world", "generic openers"]),
        "scenario": "direct",
        "delegation_source": None,
        "research_data": research_data,
        "needs_research": needs_research,
    }

    brief = _save_to_db(brief)
    return brief


def build_delegation(payload_json: str) -> dict:
    """
    Build a content brief from delegated structured research data.

    Required payload keys: format, topic, delegation_source, research_data
    """
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON payload: {exc}") from exc

    for required in ("format", "topic", "delegation_source", "research_data"):
        if required not in payload:
            raise ValueError(f"Missing required field for delegation: {required}")

    fmt = payload["format"]
    defaults = _FORMAT_DEFAULTS.get(fmt, {"tone": "neutral", "goal": "inform", "audience": "general audience"})
    research_data: dict = payload["research_data"]

    # Extract sources and key_points from research_data
    raw_sources = research_data.get("sources", [])
    sources: list = []
    for s in raw_sources:
        if isinstance(s, str):
            sources.append(s)
        elif isinstance(s, dict):
            sources.append(s.get("url", str(s)))

    # Gather key_points from various research_data fields
    key_points: list = []
    for field in ("pain_points", "key_facts", "key_points", "findings", "insights"):
        items = research_data.get(field, [])
        if isinstance(items, list):
            key_points.extend(str(i) for i in items)

    # Determine audience: research_data.target_audience takes precedence
    audience = (
        research_data.get("target_audience")
        or payload.get("audience")
        or defaults["audience"]
    )

    brief: dict = {
        "id": None,
        "format": fmt,
        "topic": payload["topic"],
        "audience": audience,
        "angle": payload.get("angle", None),
        "tone": payload.get("tone", defaults["tone"]),
        "goal": payload.get("goal", defaults["goal"]),
        "key_points": key_points,
        "sources": sources,
        "avoid": payload.get("avoid", ["In today's fast-paced world", "generic openers"]),
        "scenario": "delegation",
        "delegation_source": payload["delegation_source"],
        "research_data": research_data,
        "needs_research": False,
    }

    brief = _save_to_db(brief)
    return brief


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Content brief builder for Writer agent."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # direct
    p_direct = sub.add_parser("direct", help="Build brief from direct user request.")
    p_direct.add_argument(
        "payload",
        help='JSON string. Required keys: format, topic. Optional: audience, tone, goal, key_points, sources, angle.',
    )

    # delegation
    p_deleg = sub.add_parser("delegation", help="Build brief from delegated research data.")
    p_deleg.add_argument(
        "payload",
        help='JSON string. Required keys: format, topic, delegation_source, research_data.',
    )

    # template
    p_tmpl = sub.add_parser("template", help="Return blank brief template for a format.")
    p_tmpl.add_argument(
        "format_name",
        help="Content format (e.g. blog, linkedin, twitter_thread, newsletter, report).",
    )

    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    try:
        if args.command == "direct":
            result = build_direct(args.payload)
            print(json.dumps(result, indent=2))

        elif args.command == "delegation":
            result = build_delegation(args.payload)
            print(json.dumps(result, indent=2))

        elif args.command == "template":
            result = get_template(args.format_name)
            print(json.dumps(result, indent=2))

        else:
            parser.print_help()
            sys.exit(1)

    except ValueError as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
    except Exception as exc:
        print(json.dumps({"error": f"Unexpected error: {exc}"}))
        sys.exit(1)
