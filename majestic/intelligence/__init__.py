"""Intelligence services — reusable corpus-building and LLM helpers.

Shared by CLI analytics commands (/research, /pains, /briefing, /ideas,
/predict, /ask) and the forthcoming web API (W3). Keeping them here prevents
the handlers from growing duplicate logic and lets the web layer call the same
services without importing from the CLI layer.
"""

from majestic.intelligence.corpus import build_news_corpus
from majestic.intelligence.llm import llm_with_retry
from majestic.intelligence.briefing import load_recent_briefing
from majestic.intelligence.products import generate_solo_products, render_markdown
from majestic.intelligence.predict import generate_predictions

__all__ = [
    "build_news_corpus",
    "llm_with_retry",
    "load_recent_briefing",
    "generate_solo_products",
    "render_markdown",
    "generate_predictions",
]
