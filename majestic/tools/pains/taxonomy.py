"""Canonical domain taxonomy for pains / ideas.

A small controlled vocabulary so the ``domain`` field is consistent across runs
and across the pains and ideas pipelines — which is what makes the dataset
queryable and sellable. Free-text LLM output is mapped onto this list via
:func:`normalize_domain`; unknown values fall back to ``"other"``.
"""

from __future__ import annotations

# The allowed domains. Keep this curated and stable — it's part of the data
# contract for the intel/ tier.
CANONICAL_DOMAINS: frozenset[str] = frozenset({
    "productivity",
    "marketing",
    "devtools",
    "b2b",
    "finance",
    "hr",
    "design",
    "nocode",
    "web",
    "data",
    "ecommerce",
    "education",
    "health",
    "legal",
    "sales",
    "support",
    "security",
    "ai",
    "other",
})

# Known variants → canonical. Lets the LLM be loose while storage stays clean.
DOMAIN_ALIASES: dict[str, str] = {
    "webdev": "web",
    "web-dev": "web",
    "website": "web",
    "development": "devtools",
    "dev": "devtools",
    "developer-tools": "devtools",
    "developer tools": "devtools",
    "fintech": "finance",
    "financial": "finance",
    "saas": "b2b",
    "enterprise": "b2b",
    "marketing-tools": "marketing",
    "growth": "marketing",
    "hr-tech": "hr",
    "hrtech": "hr",
    "recruiting": "hr",
    "ux": "design",
    "ui": "design",
    "ui/ux": "design",
    "analytics": "data",
    "data-science": "data",
    "e-commerce": "ecommerce",
    "edtech": "education",
    "healthtech": "health",
    "healthcare": "health",
    "no-code": "nocode",
    "low-code": "nocode",
    "infosec": "security",
    "cybersecurity": "security",
    "cyber": "security",
    "customer-support": "support",
    "customer support": "support",
}


def normalize_domain(raw: str | None) -> str:
    """Map a free-text domain onto the canonical taxonomy.

    Lowercases/trims, resolves known aliases, accepts canonical values as-is,
    and falls back to ``"other"`` for anything unrecognized.
    """
    d = (raw or "").strip().lower()
    if not d:
        return "other"
    if d in DOMAIN_ALIASES:
        return DOMAIN_ALIASES[d]
    if d in CANONICAL_DOMAINS:
        return d
    return "other"
