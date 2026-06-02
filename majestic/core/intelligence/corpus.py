"""News corpus builder — deduplication, grouping, char budget."""

from __future__ import annotations

import re
from collections import defaultdict


def build_news_corpus(
    articles: list[dict],
    max_chars: int = 50_000,
    include_summaries: bool = True,
) -> tuple[list[str], bool]:
    """Deduplicate, group by category, build a char-bounded corpus.

    Returns (lines, capped) where *capped* is True when the budget was hit
    before all articles were included.
    """
    articles = sorted(articles, key=lambda a: a.get("date", ""), reverse=True)

    seen: set[str] = set()
    deduped: list[dict] = []
    for a in articles:
        k = " ".join(re.sub(r"[^a-z0-9 ]", "", a.get("title", "").lower()).split()[:8])
        if k and k not in seen:
            seen.add(k)
            deduped.append(a)

    by_cat: dict[str, list] = defaultdict(list)
    for a in deduped:
        by_cat[a.get("category", "general")].append(a)

    lines: list[str] = []
    chars = 0
    capped = False
    for cat, items in by_cat.items():
        header = f"=== {cat.upper()} ({len(items)} articles) ==="
        lines.append(header)
        chars += len(header)
        for a in items[:30]:
            entry = f"· [{a.get('date', '')}] {a.get('source', '')}: {a.get('title', '')}"
            lines.append(entry)
            chars += len(entry)
            if include_summaries and a.get("summary"):
                s = f"  {a.get('summary', '')[:300]}"
                lines.append(s)
                chars += len(s)
            if chars >= max_chars:
                capped = True
                break
        lines.append("")
        if capped:
            break
    return lines, capped
