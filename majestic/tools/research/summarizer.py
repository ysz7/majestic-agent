"""
Map-reduce corpus summarizer for small-context models (context < 16K tokens).

Groups articles by category, summarizes each group with a cheap LLM call
(step_type="simple"), and returns a compact corpus that fits small context windows.
Falls back to headline-only listing when summarization fails.
"""
from __future__ import annotations

from collections import defaultdict


async def build_corpus_summarized(
    articles: list[dict],
    llm_router,
    token_budget: int,
) -> tuple[list[str], bool]:
    """Summarize article groups with map-reduce and return a compact corpus.

    Each category group gets one cheap LLM call producing a 3–4 sentence summary.
    Much more compact than raw articles — enables meaningful analysis on free-tier
    models with small context windows.

    Returns (lines, capped).
    """
    by_cat: dict = defaultdict(list)
    for a in sorted(articles, key=lambda x: (x.get("score", 0.0), x.get("date", "")), reverse=True):
        by_cat[a.get("category", "general")].append(a)

    lines: list[str] = []
    chars = 0
    max_chars = token_budget * 4

    for cat, items in sorted(by_cat.items(), key=lambda x: -len(x[1])):
        if chars >= max_chars:
            lines.append("[... corpus budget reached ...]")
            return lines, True

        if len(items) < 2:
            entry = f"=== {cat.upper()} ===\n· {items[0].get('title', '')}"
            lines.extend([entry, ""])
            chars += len(entry)
            continue

        raw = "\n".join(
            f"- [{a.get('date','')}] {a.get('source','')}: {a.get('title','')}. "
            f"{a.get('summary','')[:150]}"
            for a in items[:20]
        )
        try:
            resp = await llm_router.chat(
                messages=[
                    {"role": "system", "content": "Summarize news. Be factual and brief."},
                    {"role": "user", "content": (
                        f"Summarize these {len(items)} {cat} articles in 3–4 sentences. "
                        "Include key facts, numbers, and named actors. No preamble.\n\n" + raw
                    )},
                ],
                step_type="simple",
            )
            summary = resp.get("content", "").strip()
        except Exception:
            summary = ""

        if summary:
            entry = f"=== {cat.upper()} ({len(items)} articles) ===\n{summary}"
        else:
            entry = (
                f"=== {cat.upper()} ({len(items)} articles) ===\n"
                + "\n".join(f"· {a.get('title', '')}" for a in items[:5])
            )

        lines.extend([entry, ""])
        chars += len(entry)

    return lines, False
