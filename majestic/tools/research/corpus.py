"""
Token-budget-aware corpus builder for research articles.

Replaces the hardcoded max_chars approach with a dynamic budget derived
from the model's actual context window.
"""
from __future__ import annotations

import re
from collections import defaultdict


def calc_article_budget(
    context_limit: int,
    section_fraction: float = 0.6,
    response_reserve: float = 0.25,
    instruction_tokens: int = 2_000,
) -> int:
    """Return token budget for the article section of a prompt.

    Reserves response_reserve * context_limit for the model's response,
    plus instruction_tokens for system prompt + instructions.
    section_fraction controls what share of the remaining space goes to articles.
    """
    available = int(context_limit * (1 - response_reserve)) - instruction_tokens
    return max(1_000, int(available * section_fraction))


def build_corpus(
    articles: list[dict],
    token_budget: int,
    include_summaries: bool = True,
) -> tuple[list[str], bool]:
    """Build a token-budget-aware corpus from articles, sorted by score desc then date.

    Returns (lines, capped) where capped is True when the budget was reached.
    Token budget is estimated as tokens × 4 chars (standard heuristic).
    """
    max_chars = token_budget * 4

    articles = sorted(
        articles,
        key=lambda a: (a.get("score", 0.0), a.get("date", "")),
        reverse=True,
    )

    seen: set[str] = set()
    deduped: list[dict] = []
    for a in articles:
        k = " ".join(re.sub(r"[^a-z0-9 ]", "", a.get("title", "").lower()).split()[:8])
        if k and k not in seen:
            seen.add(k)
            deduped.append(a)

    by_cat: dict = defaultdict(list)
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
            entry = f"· [{a.get('date','')}] {a.get('source','')}: {a.get('title','')}"
            lines.append(entry)
            chars += len(entry)
            if include_summaries and a.get("summary"):
                s = f"  {a.get('summary','')[:300]}"
                lines.append(s)
                chars += len(s)
            if chars >= max_chars:
                capped = True
                break
        lines.append("")
        if capped:
            break
    return lines, capped
