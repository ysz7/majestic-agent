"""Intelligence services — reusable corpus-building and LLM helpers.

Shared by CLI analytics commands (/research, /pains, /briefing, /ideas,
/predict, /ask) and the forthcoming web API (W3). Keeping them here prevents
the handlers from growing duplicate logic and lets the web layer call the same
services without importing from the CLI layer.
"""

from majestic.core.intelligence.corpus import build_news_corpus
from majestic.core.intelligence.llm import llm_with_retry
from majestic.core.intelligence.briefing import load_recent_briefing
from majestic.core.intelligence.products import generate_solo_products, render_markdown

__all__ = [
    "build_news_corpus",
    "llm_with_retry",
    "load_recent_briefing",
    "generate_solo_products",
    "render_markdown",
]
