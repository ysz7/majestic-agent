"""Context builders for LLM prompts — build structured feed summaries."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Dict

_SOURCE_TRUST: Dict[str, float] = {
    "hackernews":      1.0,
    "reddit":          0.9,
    "github_trending": 1.0,
    "newsapi":         1.0,
    "arxiv":           0.95,
    "google_trends":   0.8,
    "mastodon":        0.65,
    "devto":           0.6,
    "producthunt":     0.2,
}

_STOP_WORDS = {
    "about", "after", "again", "also", "been", "before", "being", "between",
    "could", "does", "doing", "during", "each", "from", "have", "having",
    "here", "into", "just", "like", "more", "most", "need", "only", "other",
    "over", "same", "should", "some", "such", "than", "that", "their",
    "them", "then", "there", "these", "they", "this", "those", "through",
    "under", "very", "want", "were", "what", "when", "where", "which",
    "while", "will", "with", "would", "your", "using", "build", "built",
    "make", "made", "open", "source", "project", "based", "model", "tool",
    "tools", "first", "large", "small", "data", "works", "work", "write",
}

_SRC_LABELS = {
    "hackernews":      "HACKER NEWS",
    "reddit":          "REDDIT",
    "github_trending": "GITHUB TRENDING",
    "producthunt":     "PRODUCT HUNT",
    "mastodon":        "MASTODON",
    "devto":           "DEV.TO",
    "google_trends":   "GOOGLE TRENDS",
    "newsapi":         "NEWS (WORLD)",
    "arxiv":           "ARXIV PAPERS",
}


def _lang_wrap(prompt: str) -> str:
    from majestic.config import get
    lang     = get("language", "EN")
    currency = get("currency", "USD")
    inst     = (f"IMPORTANT: You MUST respond entirely in {lang}. All text including section headers must be in {lang}. "
                f"Always use {currency} for all prices, costs, revenue estimates, and monetary values.")
    return f"{inst}\n\n{prompt}\n\n{inst}"


def _build_feed_context(hours: int = 24, max_items: int = 120) -> str:
    from majestic.tools.research.collect import load_feed
    items  = load_feed(limit=max_items)
    if not items:
        return ""
    cutoff = datetime.now() - timedelta(hours=hours)
    recent = []
    for item in items:
        try:
            ts = datetime.fromisoformat(item.get("ts", ""))
            if ts >= cutoff:
                recent.append(item)
        except Exception:
            recent.append(item)
    recent = recent[:max_items]
    if not recent:
        return ""
    sections: Dict[str, List[str]] = {}
    for item in recent:
        src   = item.get("source", "other")
        title = item.get("title", "")
        desc  = item.get("description") or item.get("selftext") or ""
        score = item.get("score") or item.get("stars") or ""
        line  = f"• {title}"
        if desc:
            line += f" — {desc[:120]}"
        if score:
            line += f" [{score}]"
        sections.setdefault(src, []).append(line)
    parts = []
    for src, lines in sections.items():
        label = _SRC_LABELS.get(src, src.upper())
        parts.append(f"=== {label} ({len(lines)} items) ===\n" + "\n".join(lines[:30]))
    return "\n\n".join(parts)


def _build_briefing_context(days: int = 30, top_per_source: int = 40) -> str:
    from majestic.tools.research.collect import load_feed
    items  = load_feed(limit=3000)
    if not items:
        return ""
    cutoff = datetime.now() - timedelta(days=days)
    recent = [i for i in items if _ts_ok(i, cutoff)]
    if not recent:
        return ""
    groups: Dict[str, list] = defaultdict(list)
    for item in recent:
        groups[item.get("source", "other")].append(item)
    parts = []
    for src, src_items in groups.items():
        sorted_items = sorted(
            src_items,
            key=lambda x: (x.get("ccw", 0), int(str(x.get("score") or x.get("stars") or 0).replace(",", "") or 0)),
            reverse=True,
        )[:top_per_source]
        lines = []
        for item in sorted_items:
            title = item.get("title", "")
            desc  = item.get("description") or item.get("selftext") or ""
            score = item.get("score") or item.get("stars") or ""
            ccw   = item.get("ccw", 0)
            line  = f"• {title}"
            if desc:
                line += f" — {desc[:100]}"
            if score:
                line += f" [{score}]"
            if ccw >= 7:
                line += f" [CCW:{ccw}]"
            lines.append(line)
        label = _SRC_LABELS.get(src, src.upper())
        parts.append(f"=== {label} ({len(src_items)} items, showing top {len(lines)}) ===\n" + "\n".join(lines))
    return "\n\n".join(parts)


def _ts_ok(item: dict, cutoff: datetime) -> bool:
    try:
        return datetime.fromisoformat(item.get("ts", "")) >= cutoff
    except Exception:
        return True


def _build_thematic_context(days: int = 14, top_per_source: int = 40) -> str:
    from majestic.tools.research.collect import load_feed
    items  = load_feed(limit=3000)
    if not items:
        return ""
    cutoff = datetime.now() - timedelta(days=days)
    recent = [i for i in items if _ts_ok(i, cutoff)]
    if not recent:
        return ""

    organic = [i for i in recent if _SOURCE_TRUST.get(i.get("source", ""), 0.5) >= 0.6]
    word_sources: Dict[str, set] = defaultdict(set)
    word_items:   Dict[str, list] = defaultdict(list)
    for item in organic:
        text = (item.get("title", "") + " " + (item.get("description") or item.get("selftext") or "")).lower()
        src  = item.get("source", "")
        for w in {w.strip(".,!?:;()[]'\"") for w in text.split() if len(w) >= 5 and w.strip(".,!?:;()[]'\"") not in _STOP_WORDS}:
            word_sources[w].add(src)
            word_items[w].append(item)

    clusters = {w: {"sources": srcs, "items": word_items[w]} for w, srcs in word_sources.items() if len(srcs) >= 2}
    item_best: Dict[str, str] = {}
    for w, data in sorted(clusters.items(), key=lambda x: -len(x[1]["sources"])):
        for item in data["items"]:
            title = item.get("title", "")
            if title not in item_best:
                item_best[title] = w

    parts: List[str] = ["=== CONFIRMED CROSS-SOURCE THEMES ===\n(Each theme appears in 2+ independent organic sources)\n"]
    seen: set = set()
    for w, data in sorted(clusters.items(), key=lambda x: -len(x[1]["sources"]))[:18]:
        srcs_str = " + ".join(sorted(data["sources"]))
        lines: List[str] = []
        for item in data["items"]:
            title = item.get("title", "")
            if item_best.get(title) != w or title in seen:
                continue
            seen.add(title)
            src   = item.get("source", "")
            score = item.get("score") or item.get("stars") or ""
            desc  = (item.get("description") or item.get("selftext") or "")[:80]
            line  = f"  [{src}] {title}"
            if desc:
                line += f" — {desc}"
            if score:
                line += f" ({score})"
            lines.append(line)
            if len(lines) >= 4:
                break
        if lines:
            parts.append(f"\n── Theme [{w.upper()}] | {len(data['sources'])} sources: {srcs_str} ──\n" + "\n".join(lines))

    grouped: Dict[str, list] = defaultdict(list)
    for item in organic:
        src   = item.get("source", "")
        title = item.get("title", "")
        if title not in seen and _SOURCE_TRUST.get(src, 0) >= 0.6:
            grouped[src].append(item)
    single_parts: List[str] = []
    for src, src_items in grouped.items():
        label = _SRC_LABELS.get(src, src.upper())
        sorted_items = sorted(src_items, key=lambda x: int(str(x.get("score") or x.get("stars") or 0).replace(",", "") or 0), reverse=True)[:15]
        lines = [f"  • {item.get('title', '')}" + (f" ({item.get('score') or item.get('stars','')})" if (item.get("score") or item.get("stars")) else "") for item in sorted_items]
        if lines:
            single_parts.append(f"[{label}]\n" + "\n".join(lines))
    if single_parts:
        parts.append("\n\n=== SINGLE-SOURCE SIGNALS (weaker) ===\n" + "\n".join(single_parts))

    ph_items = [i for i in recent if i.get("source") == "producthunt"]
    if ph_items:
        ph_lines = [f"  • {i.get('title','')}" + (f" — {i.get('description','')[:70]}" if i.get("description") else "") for i in ph_items[:15]]
        parts.append("\n\n=== PRODUCT HUNT LAUNCHES (marketing posts — niche exists, demand NOT confirmed) ===\n" + "\n".join(ph_lines))

    return "\n".join(parts)
