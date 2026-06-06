"""News corpus builder — thin delegate to the canonical renderer.

Phase K.6: the dedup/group/budget logic lives once in
``majestic.tools.research.corpus``. This module keeps the ``build_news_corpus``
name (char-budget API) so existing imports stay valid.
"""

from __future__ import annotations

from majestic.tools.research.corpus import render_corpus


def build_news_corpus(
    articles: list[dict],
    max_chars: int = 50_000,
    include_summaries: bool = True,
) -> tuple[list[str], bool]:
    """Deduplicate, group by category, build a char-bounded corpus.

    Returns (lines, capped) — *capped* is True when the budget was hit before
    all articles were included. Delegates to the canonical renderer.
    """
    return render_corpus(articles, max_chars, include_summaries)
