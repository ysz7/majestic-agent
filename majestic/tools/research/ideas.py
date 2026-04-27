"""Business ideas tool — generates startup/product ideas from recent trends."""
from __future__ import annotations

from datetime import datetime

from majestic.tools.registry import tool
from majestic.constants import WORKSPACE_DIR, MAJESTIC_HOME

_IDEAS_LOG = MAJESTIC_HOME / "ideas_log.json"

IDEAS_PROMPT = """You are a business idea generator for a solo entrepreneur.

Below are signals organized by reliability level:
- CONFIRMED signals appear across 2+ independent organic sources — these are real trends
- SINGLE-SOURCE signals may be noise — only use if they directly reinforce a CONFIRMED signal
- PRODUCT HUNT items are company marketing posts — niche exists but market demand is NOT confirmed

=== SIGNALS ===
{context}

---

STRICT VALIDATION RULES:
1. Every idea MUST be grounded in a CONFIRMED signal (2+ independent sources).
2. "Signal" field MUST cite specific confirmed items: source + title + score/stars.
3. A Product Hunt launch that gets discussed on Reddit is ONE company's marketing — NOT confirmation.

Generate exactly 5 business ideas. Each must be:
- Buildable by one person in 2–6 weeks
- Grounded in CONFIRMED cross-source signals
- Have clear monetization

For each idea use this exact format:

### 💡 Idea N: [Name]

**Core:** [one sentence — what it is]
**Signal:** [MUST name specific confirmed items: source + title + score, minimum 2 independent]
**How to build:** [3 concrete steps]
**Monetization:** [how to earn and realistic numbers]
**Complexity:** [🟢 Low / 🟡 Medium / 🔴 High]
**Window:** [how long before this niche gets crowded]

---

After 5 ideas add:
### 🏆 Start with Idea N
[2 sentences — signal strength and timing]
"""


@tool(
    name="generate_ideas",
    description=(
        "Generate 5 business or product ideas based on recent tech and market trends. "
        "Use when the user asks for ideas, startup ideas, or business opportunities."
    ),
    input_schema={"type": "object", "properties": {}},
)
def generate_ideas() -> str:
    return _generate_ideas(force=True)


def _load_log() -> list:
    import json
    if _IDEAS_LOG.exists():
        try:
            return json.loads(_IDEAS_LOG.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_log(entries: list) -> None:
    import json
    _IDEAS_LOG.parent.mkdir(parents=True, exist_ok=True)
    _IDEAS_LOG.write_text(json.dumps(entries[-500:], ensure_ascii=False, indent=1), encoding="utf-8")


def _generate_ideas(force: bool = False) -> str:
    if not force:
        log = _load_log()
        if log:
            last = log[-1]
            try:
                last_dt = datetime.fromisoformat(last["ts"])
                if (datetime.now() - last_dt).total_seconds() < 20 * 3600:
                    return last.get("ideas", "Ideas already generated today. Use force=True to regenerate.")
            except Exception:
                pass

    from majestic.tools.research.intel_context import _build_thematic_context, _lang_wrap
    context = _build_thematic_context(days=14)
    if not context:
        return "No data for idea generation. Run /research first."

    from majestic.config import get
    lang     = get("language", "EN")
    currency = get("currency", "USD")
    _lang_inst = (
        f"IMPORTANT: You MUST respond entirely in {lang}. All text including section headers must be in {lang}. "
        f"Always use {currency} for all prices, costs, revenue estimates, and monetary values."
    )
    raw_prompt = IDEAS_PROMPT.format(context=context[:6000])
    prompt     = f"{_lang_inst}\n\n{raw_prompt}\n\n{_lang_inst}"

    from majestic.llm import get_provider
    from majestic.token_tracker import track
    try:
        resp = get_provider().complete([{"role": "user", "content": prompt}])
        try:
            um = resp.usage
            if um:
                track(um.input_tokens or 0, um.output_tokens or 0, "agent.ideas")
        except Exception:
            pass
        ideas = resp.content
    except Exception as e:
        return f"Ideas generation error: {e}"

    log = _load_log()
    log.append({"ts": datetime.now().isoformat(), "ideas": ideas})
    _save_log(log)

    try:
        (WORKSPACE_DIR / "ideas").mkdir(parents=True, exist_ok=True)
        (WORKSPACE_DIR / "ideas" / f"ideas_{datetime.now().strftime('%Y%m%d')}.md").write_text(
            f"# 💡 Ideas — {datetime.now().strftime('%Y-%m-%d')}\n\n{ideas}", encoding="utf-8"
        )
    except Exception:
        pass

    return ideas


def get_ideas_history(limit: int = 7) -> list:
    return list(reversed(_load_log()))[:limit]
