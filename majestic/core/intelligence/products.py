"""Solo Product Forge — generate a ranked TOP-N of sellable solo digital
products and micro-businesses from accumulated intelligence.

Shared by the CLI `/products` command, the desktop API, and the workflow
ActionNode so all three surfaces produce identical, structured output.

The LLM returns a JSON array of product objects (the monetization-audit
schema). We recompute the sellability score deterministically from the
per-factor breakdown so the ranking is defensible, then render markdown.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict

from majestic.core.intelligence.llm import llm_with_retry

# Sellability composite weights (sum = 1.0). See PLAN.md Phase I.3.
_WEIGHTS = {
    "demand":           0.30,
    "trend":            0.20,
    "competition_gap":  0.20,
    "solo_feasibility": 0.15,
    "margin_speed":     0.15,
}

_PRODUCT_TYPES = (
    "template | course | micro-SaaS | extension | prompt-pack | dataset | "
    "newsletter | community | productized-service"
)


def _build_corpus(
    articles: list[dict],
    pains: list[dict],
    briefing: str,
    past_names: list[str],
    days: int,
) -> str:
    """Assemble the intelligence corpus block fed to the model."""
    corpus: list[str] = [f"INTELLIGENCE CORPUS -- last {days} days\n"]

    if briefing:
        cap = briefing[:6_000] + ("\n[... truncated ...]" if len(briefing) > 6_000 else "")
        corpus.append("=== MACRO SYNTHESIS (from /briefing) ===\n")
        corpus.append(cap)
        corpus.append("")

    high = [p for p in pains if p.get("intensity") == "HIGH" or p.get("willingness_to_pay")]
    if high:
        corpus.append(f"=== HIGH-DEMAND SIGNALS ({len(high)} pains — strongest, WTP/HIGH) ===\n")
        c = 0
        for p in high[:60]:
            src = f"[{p.get('source','')}] " if p.get("source") else ""
            wtp = " WTP" if p.get("willingness_to_pay") else ""
            line = f"· {src}[{p.get('intensity','H')}] {p.get('pain_text','')}{wtp}"
            corpus.append(line)
            c += len(line)
            if c >= 12_000:
                break
        corpus.append("")

    regular = [p for p in pains if p not in high]
    if regular:
        by_dom: dict = defaultdict(list)
        for p in regular:
            by_dom[p.get("domain", "other")].append(p)
        corpus.append(f"=== DEMAND & PAIN SIGNALS ({len(regular)} more) ===\n")
        c = 0
        for dom, items in sorted(by_dom.items(), key=lambda x: -len(x[1])):
            corpus.append(f"[{dom.upper()} -- {len(items)}]")
            for p in items[:15]:
                line = f"· [{p.get('source','')}] {p.get('pain_text','')}"
                corpus.append(line)
                c += len(line)
                if c >= 12_000:
                    break
            corpus.append("")
            if c >= 12_000:
                break

    launches = [a for a in articles if a.get("category") == "launches"]
    news = [a for a in articles if a.get("category") != "launches"]

    if news:
        corpus.append(f"=== MARKET & NEWS SIGNALS ({len(news)} articles) ===\n")
        c = 0
        for a in news[:50]:
            line = f"· [{a.get('date','')}] {a.get('title','')}"
            corpus.append(line)
            if a.get("summary"):
                s = f"  {a.get('summary','')[:180]}"
                corpus.append(s)
                c += len(s)
            c += len(line)
            if c >= 14_000:
                break
        corpus.append("")

    if launches:
        corpus.append(f"=== MARKET LAUNCHES — {len(launches)} on ProductHunt (assess competition) ===\n")
        for l in launches[:30]:
            corpus.append(f"· [{l.get('date','')}] {l.get('title','')}")
            if l.get("summary"):
                corpus.append(f"  {l.get('summary','')[:160]}")
        corpus.append("")

    if past_names:
        corpus.append("=== ALREADY GENERATED (do NOT repeat — find NEW angles) ===")
        corpus.append("· " + " · ".join(past_names[:20]))
        corpus.append("")

    return "\n".join(corpus)


def _instructions(n: int, lang_rule: str) -> str:
    return (
        f"{lang_rule}"
        f"TASK: From the corpus, identify the TOP {n} MOST SELLABLE digital products and "
        "solo micro-businesses a SINGLE person can build and run. Types: "
        f"{_PRODUCT_TYPES}.\n\n"
        "RULES:\n"
        "- Solo-first: one person must be able to build AND sell it.\n"
        "- Every item must be grounded in REAL corpus signals (cite specific pains/articles).\n"
        "- Rank by a composite sellability score (see score_breakdown factors).\n"
        "- Be tactical and specific — name the EXACT tools to build it and the EXACT channels "
        "to sell it (the 'secret' stack & distribution a paid research tool would give).\n"
        "- No filler, no generic SaaS clichés.\n\n"
        "OUTPUT: Return ONLY a JSON array of exactly "
        f"{n} objects. No prose before or after. Each object:\n"
        "{\n"
        '  "name": str,\n'
        f'  "type": one of [{_PRODUCT_TYPES}],\n'
        '  "one_liner": str,\n'
        '  "audience": str (the solo-buyer persona),\n'
        '  "demand": str (cite specific pains + intensity + WTP from corpus),\n'
        '  "why_now": str (trend signal from research/launches),\n'
        '  "score_breakdown": {"demand":0-100,"trend":0-100,"competition_gap":0-100,'
        '"solo_feasibility":0-100,"margin_speed":0-100},\n'
        '  "monetization_audit": {"pricing_model":str,"price_points":str,'
        '"revenue_range":str,"margin":str,"time_to_first_dollar":str,"build_effort":str},\n'
        '  "build_stack": [str] (exact tools/platforms/AI to ship solo),\n'
        '  "distribution": [str] (exact channels: marketplaces, SEO keywords, communities, tactics),\n'
        '  "competition_gap": str (what exists -> the wedge),\n'
        '  "unfair_advantage": str (why a solo can win),\n'
        '  "validation_test": str (kill check in 14-30 days),\n'
        '  "first_3_steps": [str, str, str]\n'
        "}\n"
        "Return strictly valid JSON (double quotes, no trailing commas, no comments)."
    )


def _salvage_objects(s: str) -> list[dict]:
    """Recover every complete top-level ``{...}`` object from *s*.

    Survives a truncated/malformed array (e.g. the model hit max_tokens) by
    parsing each balanced object independently and dropping only the broken
    trailing one. String-aware so braces inside values don't confuse depth.
    """
    out: list[dict] = []
    depth = 0
    start = -1
    in_str = False
    esc = False
    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    blob = s[start : i + 1]
                    try:
                        out.append(json.loads(blob))
                    except json.JSONDecodeError:
                        try:
                            out.append(json.loads(re.sub(r",\s*([\]}])", r"\1", blob)))
                        except json.JSONDecodeError:
                            pass
                    start = -1
    return [o for o in out if isinstance(o, dict)]


def _extract_json_array(text: str) -> list[dict]:
    """Pull product objects out of an LLM response, tolerant of common breakage.

    Handles: markdown code fences, object-wrapped arrays, trailing commas, and
    truncated output (recovers complete objects via :func:`_salvage_objects`).
    """
    # Strip markdown code fences if present.
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)

    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        blob = text[start : end + 1]
        try:
            data = json.loads(blob)
            if isinstance(data, list):
                return [o for o in data if isinstance(o, dict)]
        except json.JSONDecodeError:
            try:
                data = json.loads(re.sub(r",\s*([\]}])", r"\1", blob))
                if isinstance(data, list):
                    return [o for o in data if isinstance(o, dict)]
            except json.JSONDecodeError:
                pass

    # Fallback: salvage complete objects (handles truncation / wrapping).
    return _salvage_objects(text)


def _score(item: dict) -> int:
    """Recompute the composite sellability score from the per-factor breakdown."""
    bd = item.get("score_breakdown") or {}
    total = 0.0
    for factor, weight in _WEIGHTS.items():
        try:
            total += float(bd.get(factor, 0)) * weight
        except (TypeError, ValueError):
            pass
    return round(total)


def render_markdown(items: list[dict], days: int) -> str:
    """Render the structured product list as a readable markdown report."""
    if not items:
        return "## Solo Product Forge\n\nNo sellable opportunities found in the current corpus."

    lines = [
        "## Solo Product Forge — TOP opportunities",
        f"*Ranked by sellability · synthesized from the last {days} days of intelligence*",
        "",
    ]
    for i, it in enumerate(items, 1):
        ma = it.get("monetization_audit") or {}
        lines.append(f"### #{i} — {it.get('name','?')}  ·  {it.get('sellability_score','?')}/100")
        lines.append(f"*{it.get('type','')}* — {it.get('one_liner','')}")
        lines.append(f"**For:** {it.get('audience','')}")
        lines.append(f"**Demand:** {it.get('demand','')}")
        lines.append(f"**Why now:** {it.get('why_now','')}")
        lines.append("")
        lines.append("**Monetization audit**")
        lines.append(f"- Pricing: {ma.get('pricing_model','')} — {ma.get('price_points','')}")
        lines.append(f"- Revenue: {ma.get('revenue_range','')}  ·  Margin: {ma.get('margin','')}")
        lines.append(f"- Time to first $: {ma.get('time_to_first_dollar','')}  ·  "
                     f"Build: {ma.get('build_effort','')}")
        lines.append("")
        stack = it.get("build_stack") or []
        chan = it.get("distribution") or []
        lines.append(f"**Build stack:** {', '.join(stack) if isinstance(stack, list) else stack}")
        lines.append(f"**Distribution:** {', '.join(chan) if isinstance(chan, list) else chan}")
        lines.append(f"**Competition gap:** {it.get('competition_gap','')}")
        lines.append(f"**Unfair advantage:** {it.get('unfair_advantage','')}")
        lines.append(f"**Validation:** {it.get('validation_test','')}")
        steps = it.get("first_3_steps") or []
        if isinstance(steps, list) and steps:
            lines.append("**First steps:** " + " → ".join(str(s) for s in steps))
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


async def generate_solo_products(
    *,
    llm,
    articles: list[dict] | None = None,
    pains: list[dict] | None = None,
    briefing: str = "",
    past_names: list[str] | None = None,
    n: int = 10,
    days: int = 30,
    lang: str = "en",
) -> dict:
    """Generate the TOP-N solo products.

    Returns
    -------
    dict with keys: ``items`` (list[dict], scored + sorted), ``markdown`` (str),
    ``tokens`` (int), ``cost`` (float).
    """
    articles = articles or []
    pains = pains or []
    past_names = past_names or []

    is_non_en = lang and lang.lower() not in ("en", "english")
    lang_rule = (
        f"LANGUAGE: Write all human-readable string values in {lang}. "
        "JSON keys stay in English. "
    ) if is_non_en else ""

    corpus = _build_corpus(articles, pains, briefing, past_names, days)
    instructions = _instructions(n, lang_rule)

    system = (
        "You are a world-class solo-business strategist and monetization analyst. "
        "You output ONLY valid JSON — no markdown, no preamble, no commentary."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": corpus + "\n\n" + instructions},
    ]

    # 10 fully-audited products need plenty of output headroom — the default
    # 4096 cap truncates the JSON array. Request a larger completion budget.
    resp = await llm_with_retry(llm, messages, step_type="reason", max_tokens=8192)
    content = resp.get("content", "")
    tokens = resp.get("input_tokens", 0) + resp.get("output_tokens", 0)
    cost = resp.get("cost") or 0.0
    if not cost and tokens:
        try:
            from majestic.llm.base import BaseLLM
            cost = BaseLLM._estimate_cost(
                resp.get("input_tokens", 0), resp.get("output_tokens", 0)
            )
        except Exception:
            pass

    items = _extract_json_array(content)
    for it in items:
        if isinstance(it, dict):
            it["sellability_score"] = _score(it)
    items = [it for it in items if isinstance(it, dict)]
    items.sort(key=lambda x: x.get("sellability_score", 0), reverse=True)
    items = items[:n]

    return {
        "items": items,
        "markdown": render_markdown(items, days),
        "tokens": tokens,
        "cost": cost,
        "raw": content,
    }


async def run_for_profile(profile: str, days: int = 30, n: int = 10) -> dict:
    """End-to-end run for a profile: gather corpus, generate, persist.

    Used by the desktop API and the workflow ``product_forge`` node so they
    share identical data-gathering and storage. Returns
    ``{date, items, markdown}``.

    Raises
    ------
    ValueError
        If there is no research/pains data to work from.
    """
    import json as _json
    from datetime import date

    from majestic.config.settings import Settings
    from majestic.storage import get_backend
    from majestic.llm.router import LLMRouter
    from majestic.core.intelligence.briefing import load_recent_briefing

    settings = Settings(profile)
    backend = get_backend(settings)

    articles: list[dict] = []
    try:
        rdb = backend.research()
        articles = rdb.get_articles(days=days)
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

    prod_dir = settings.workspace_dir / "products"
    past_names: list[str] = []
    if prod_dir.exists():
        for f in sorted(prod_dir.glob("*.json"), reverse=True)[:3]:
            try:
                data = _json.loads(f.read_text(encoding="utf-8"))
                past_names.extend(it.get("name", "") for it in data if isinstance(it, dict))
            except Exception:
                pass

    llm = LLMRouter(settings)
    out = await generate_solo_products(
        llm=llm,
        articles=articles,
        pains=pains,
        briefing=briefing,
        past_names=past_names,
        n=n,
        days=days,
        lang=getattr(settings, "agent_language", "") or "en",
    )

    today = date.today().isoformat()
    prod_dir.mkdir(parents=True, exist_ok=True)
    (prod_dir / f"{today}.md").write_text(out["markdown"], encoding="utf-8")
    if out["items"]:
        (prod_dir / f"{today}.json").write_text(
            _json.dumps(out["items"], indent=2, ensure_ascii=False), encoding="utf-8"
        )
    else:
        # Parsing produced nothing — keep the raw LLM output for diagnosis.
        (prod_dir / f"{today}.raw.txt").write_text(out.get("raw", ""), encoding="utf-8")

    return {"date": today, "items": out["items"], "markdown": out["markdown"]}
