"""Predict v2 — single-section, real-data, cross-sector forecasts (Phase J).

Produces ONE ranked list of strong predictions, each ``prediction + reason``,
grounded in the real research/prices corpus. Models the probability that
niches and sectors touch (cross-sector ripple) using actual corpus
co-occurrence as evidence.

  - 4 anchor niches are always tracked; their reading is compared run-to-run.
  - Auto niches emerge from the news/pains signal volume.
  - Only STRONG, well-grounded predictions surface (no filler).

Output is a JSON array (parsed for the UI) rendered to a single markdown
section. Reuses the robust JSON salvage from the products service.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from majestic.intelligence.llm import llm_with_retry
from majestic.intelligence.products import _extract_json_array

# Keyword sets used to detect anchor niches in article text for co-occurrence.
_ANCHOR_KEYWORDS: dict[str, list[str]] = {
    "Crypto (BTC/ETH)": [
        "bitcoin", "btc", "ethereum", "eth", "crypto", "stablecoin", "defi",
        "altcoin", "binance", "coinbase", "etf",
    ],
    "AI / Tech": [
        "ai", "artificial intelligence", "llm", "gpt", "openai", "anthropic",
        "nvidia", "model", "machine learning", "chip", "semiconductor", "saas",
    ],
    "Macro + geopolitics": [
        "fed", "rate", "inflation", "cpi", "dollar", "usd", "oil", "treasury",
        "yield", "recession", "war", "sanction", "election", "tariff", "geopolit",
    ],
    "Stock markets": [
        "stock", "s&p", "sp500", "nasdaq", "dow", "equit", "shares", "earnings",
        "ipo", "index", "bond", "market cap",
    ],
}


def _anchor_hits(articles: list[dict], anchors: list[str]) -> tuple[dict, dict]:
    """Count per-anchor article hits and pairwise co-occurrence in the corpus."""
    counts: dict[str, int] = {a: 0 for a in anchors}
    pairs: dict[tuple[str, str], int] = defaultdict(int)

    for art in articles:
        text = f"{art.get('title','')} {art.get('summary','')}".lower()
        present = []
        for anchor in anchors:
            kws = _ANCHOR_KEYWORDS.get(anchor, [])
            if any(kw in text for kw in kws):
                counts[anchor] += 1
                present.append(anchor)
        for i in range(len(present)):
            for j in range(i + 1, len(present)):
                key = tuple(sorted((present[i], present[j])))
                pairs[key] += 1

    return counts, dict(pairs)


def _cooccurrence_block(counts: dict, pairs: dict, total: int) -> str:
    """Render real co-occurrence evidence so intersection probabilities are data-driven."""
    lines = ["=== CROSS-SECTOR CO-OCCURRENCE (real corpus evidence) ===",
             f"[Out of {total} articles — how often anchor niches are mentioned together]\n"]
    lines.append("Per-niche mentions:")
    for niche, c in sorted(counts.items(), key=lambda x: -x[1]):
        lines.append(f"· {niche}: {c}")
    if pairs:
        lines.append("\nCo-mentions (both in same article — proxy for sector contact):")
        for (a, b), c in sorted(pairs.items(), key=lambda x: -x[1]):
            lines.append(f"· {a}  x  {b}: {c}")
    lines.append("")
    return "\n".join(lines)


def _auto_niches(articles: list[dict], pains: list[dict], anchors: list[str], top: int = 8) -> list[str]:
    """Emergent niches beyond the anchors, ranked by signal volume."""
    vol: dict[str, int] = defaultdict(int)
    for a in articles:
        cat = (a.get("category") or "").strip().lower()
        if cat and cat != "launches":
            vol[cat] += 1
    for p in pains:
        dom = (p.get("domain") or "").strip().lower()
        if dom and dom != "other":
            vol[dom] += 1

    anchor_lc = " ".join(anchors).lower()
    out = []
    for name, _ in sorted(vol.items(), key=lambda x: -x[1]):
        if name in anchor_lc:
            continue
        out.append(name)
        if len(out) >= top:
            break
    return out


def _anchors_file(workspace_dir: Path) -> Path:
    return workspace_dir / "predictions" / "_anchors.json"


def _load_prev_anchors(workspace_dir: Path) -> dict:
    f = _anchors_file(workspace_dir)
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_anchors(workspace_dir: Path, items: list[dict]) -> None:
    """Persist current anchor readings so the next run can show fluctuation."""
    readings = {}
    for it in items:
        if it.get("anchor") and it.get("niche"):
            readings[it["niche"]] = {
                "direction":   it.get("direction", ""),
                "probability": it.get("probability", 0),
            }
    if not readings:
        return
    f = _anchors_file(workspace_dir)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(readings, indent=2, ensure_ascii=False), encoding="utf-8")


def _apply_trend(items: list[dict], prev: dict) -> None:
    """Attach a run-to-run delta string to anchor predictions."""
    for it in items:
        if not it.get("anchor"):
            continue
        p = prev.get(it.get("niche", ""))
        if p:
            it["trend"] = f"{p.get('probability', '?')}% {p.get('direction','')} -> " \
                          f"{it.get('probability','?')}% {it.get('direction','')}"


def _instructions(anchors: list[str], auto: list[str], lang_rule: str) -> str:
    anchor_list = "\n".join(f"  - {a}" for a in anchors)
    auto_list = ", ".join(auto) if auto else "(none detected — derive from the news)"
    return (
        f"{lang_rule}"
        "TASK: Produce ONE ranked list of STRONG, well-grounded predictions.\n\n"
        "ALWAYS include one prediction for each ANCHOR niche (even if quiet):\n"
        f"{anchor_list}\n\n"
        f"Then add predictions for the strongest AUTO niches from the data: {auto_list}.\n\n"
        "HARD RULES:\n"
        "- Ground EVERY prediction in >=2 real corpus items (article/price/pain) with source + date.\n"
        "- Anchor predictions must reference the actual price reading where available.\n"
        "- Model the CROSS-SECTOR link: use the co-occurrence evidence to set a realistic "
        "intersection probability (how a move in one niche reaches another).\n"
        "- Only include STRONG predictions you can defend. OMIT weak/ungrounded ones — do NOT pad.\n"
        "- No multi-section report. No executive summary. Just the list.\n\n"
        "OUTPUT: Return ONLY a JSON array. No prose before/after. Each object:\n"
        "{\n"
        '  "niche": str,\n'
        '  "anchor": bool (true if it is one of the anchor niches),\n'
        '  "prediction": str (the specific claim),\n'
        '  "direction": "up" | "down" | "flat",\n'
        '  "horizon": str (e.g. "1-2w", "1-3m", "6-12m"),\n'
        '  "probability": int (0-100),\n'
        '  "reason": str (causal chain grounded in the cited evidence),\n'
        '  "evidence": [str, str] (>=2 cited items: "[source date] fact"),\n'
        '  "cross_sector": {"niche": str, "direction": "up"|"down"|"flat", '
        '"probability": int, "note": str}\n'
        "}\n"
        "Order: anchors first, then auto niches by probability. Strictly valid JSON."
    )


def render_markdown(items: list[dict], days: int) -> str:
    if not items:
        return "## Predictions\n\nNo strong, grounded predictions from the current corpus."
    lines = [
        "## Predictions",
        f"*One section · strong & grounded only · last {days} days of intelligence*",
        "",
    ]
    for it in items:
        arrow = {"up": "↑", "down": "↓", "flat": "→"}.get(it.get("direction", ""), "")
        tag = f" [{it.get('horizon','')}]" if it.get("horizon") else ""
        anchor_mark = " ⚓" if it.get("anchor") else ""
        lines.append(f"### {arrow} {it.get('prediction','?')} — {it.get('probability','?')}%{tag}{anchor_mark}")
        lines.append(f"*{it.get('niche','')}*")
        lines.append(f"**Reason:** {it.get('reason','')}")
        ev = it.get("evidence") or []
        if isinstance(ev, list) and ev:
            for e in ev:
                lines.append(f"- {e}")
        cs = it.get("cross_sector") or {}
        if cs.get("niche"):
            cs_arrow = {"up": "↑", "down": "↓", "flat": "→"}.get(cs.get("direction", ""), "")
            lines.append(f"**Cross-sector:** {cs_arrow} {cs.get('niche','')} "
                         f"({cs.get('probability','?')}%) — {cs.get('note','')}")
        if it.get("trend"):
            lines.append(f"**Trend:** {it['trend']}")
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


async def generate_predictions(
    *,
    llm,
    articles: list[dict] | None = None,
    pains: list[dict] | None = None,
    briefing: str = "",
    prices_block: str = "",
    anchors: list[str] | None = None,
    days: int = 30,
    lang: str = "en",
) -> dict:
    """Generate the single-section prediction list. Returns
    ``{items, markdown, tokens, cost, raw}`` (items unsorted-by-trend here)."""
    articles = articles or []
    pains = pains or []
    anchors = anchors or ["Crypto (BTC/ETH)", "AI / Tech", "Macro + geopolitics", "Stock markets"]

    counts, pairs = _anchor_hits(articles, anchors)
    auto = _auto_niches(articles, pains, anchors)

    is_non_en = lang and lang.lower() not in ("en", "english")
    lang_rule = (
        f"LANGUAGE: Write all human-readable string values in {lang}. JSON keys stay in English. "
    ) if is_non_en else ""

    corpus: list[str] = [f"INTELLIGENCE CORPUS -- last {days} days\n"]
    if prices_block:
        corpus.append(prices_block)
    if briefing:
        cap = briefing[:6_000] + ("\n[... truncated ...]" if len(briefing) > 6_000 else "")
        corpus.append("=== MACRO SYNTHESIS (from /briefing) ===\n")
        corpus.append(cap)
        corpus.append("")

    corpus.append(_cooccurrence_block(counts, pairs, len(articles)))

    if articles:
        corpus.append(f"=== NEWS & MARKET SIGNALS ({len(articles)} articles) ===\n")
        c = 0
        for a in articles[:60]:
            line = f"· [{a.get('date','')}] {a.get('title','')}"
            corpus.append(line)
            if a.get("summary"):
                s = f"  {a.get('summary','')[:160]}"
                corpus.append(s)
                c += len(s)
            c += len(line)
            if c >= 14_000:
                break
        corpus.append("")

    if pains:
        by_dom: dict = defaultdict(list)
        for p in pains:
            by_dom[p.get("domain", "other")].append(p)
        corpus.append(f"=== DEMAND & PAIN SIGNALS ({len(pains)} pains) ===\n")
        c = 0
        for dom, items_ in sorted(by_dom.items(), key=lambda x: -len(x[1])):
            corpus.append(f"[{dom.upper()} -- {len(items_)}]")
            for p in items_[:12]:
                line = f"· [{p.get('source','')}] {p.get('pain_text','')}"
                corpus.append(line)
                c += len(line)
                if c >= 10_000:
                    break
            if c >= 10_000:
                break
        corpus.append("")

    instructions = _instructions(anchors, auto, lang_rule)
    system = (
        "You are a professional intelligence analyst trained in Superforecasting. "
        "You synthesize MULTIPLE independent signals and output ONLY valid JSON — "
        "no markdown, no preamble, no commentary. Calibrated probabilities only."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": "\n".join(corpus) + "\n\n" + instructions},
    ]

    resp = await llm_with_retry(llm, messages, step_type="reason", max_tokens=8192)
    content = resp.get("content", "")
    tokens = resp.get("input_tokens", 0) + resp.get("output_tokens", 0)
    cost = resp.get("cost") or 0.0
    if not cost and tokens:
        try:
            from majestic.llm.base import BaseLLM
            cost = BaseLLM._estimate_cost(resp.get("input_tokens", 0), resp.get("output_tokens", 0))
        except Exception:
            pass

    items = _extract_json_array(content)
    # Anchors first, then by probability.
    def _key(it: dict):
        return (0 if it.get("anchor") else 1, -int(it.get("probability", 0) or 0))
    items = sorted([it for it in items if isinstance(it, dict)], key=_key)

    return {
        "items": items,
        "markdown": render_markdown(items, days),
        "tokens": tokens,
        "cost": cost,
        "raw": content,
    }


async def run_for_profile(profile: str, days: int = 30) -> dict:
    """End-to-end run for a profile: gather corpus, generate, apply fluctuation,
    persist. Shared by the desktop API. Returns ``{date, items, markdown}``."""
    from datetime import date

    from majestic.config.settings import Settings
    from majestic.storage import get_backend
    from majestic.llm.router import LLMRouter
    from majestic.intelligence.briefing import load_recent_briefing

    settings = Settings(profile)
    backend = get_backend(settings)

    articles: list[dict] = []
    prices_block = ""
    try:
        rdb = backend.research()
        articles = rdb.get_articles(days=days)
        try:
            prices, prices_ts = rdb.get_latest_prices()
            if prices:
                from majestic.tools.research.prices import format_prices_for_corpus as _fmt
                prices_block = _fmt(prices, prices_ts) or ""
        except Exception:
            pass
        rdb.close()
    except Exception:
        pass

    pains: list[dict] = []
    try:
        pdb = backend.pains()
        pains = pdb.get_pains(days=days)
        pdb.close()
    except Exception:
        pass

    if not articles and not pains:
        raise ValueError("No intelligence data — run /research and /pains first.")

    briefing = load_recent_briefing(settings, max_days=3) or ""

    out = await generate_predictions(
        llm=LLMRouter(settings),
        articles=articles,
        pains=pains,
        briefing=briefing,
        prices_block=prices_block,
        anchors=settings.anchor_niches,
        days=days,
        lang=getattr(settings, "agent_language", "") or "en",
    )

    ws = settings.workspace_dir
    prev = _load_prev_anchors(ws)
    _apply_trend(out["items"], prev)
    out["markdown"] = render_markdown(out["items"], days)
    _save_anchors(ws, out["items"])

    today = date.today().isoformat()
    pred_dir = ws / "predictions"
    pred_dir.mkdir(parents=True, exist_ok=True)
    (pred_dir / f"{today}.md").write_text(out["markdown"], encoding="utf-8")
    if out["items"]:
        (pred_dir / f"{today}.json").write_text(
            json.dumps(out["items"], indent=2, ensure_ascii=False), encoding="utf-8"
        )
    else:
        (pred_dir / f"{today}.raw.txt").write_text(out.get("raw", ""), encoding="utf-8")

    return {"date": today, "items": out["items"], "markdown": out["markdown"]}
