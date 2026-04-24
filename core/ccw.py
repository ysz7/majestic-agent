"""
CCW — Can it Change the World?

Per-item score 0–10 added to every new intel item during research.

Strategy: top-40 items by engagement → one LLM batch call (titles only).
Cost: ~$0.008 per research cycle at ~40 items.

Fields added to each item:
  ccw         : int  0–10
  ccw_reason  : str  one-sentence explanation from LLM
"""

import re as _re
import json as _json
from typing import List, Dict


# ── Scoring ────────────────────────────────────────────────────────────────────

_CCW_PROMPT = """You are evaluating news/tech items for their potential to change the world.

For each item below, assign a CCW score (0–10):
  10 — civilisation-altering: AGI, nuclear war, pandemic cure, fusion breakthrough
   9 — major scientific/medical breakthrough or global crisis
   8 — significant geopolitical/economic/tech event with wide impact
   7 — notable but narrower impact
   5-6 — interesting, some impact
   1-4 — routine news, product launches, tutorials, opinion pieces
   0   — noise, ads, self-promotion

Items (title only):
{items}

Respond as a compact JSON array — one object per item, in the same order:
[{{"i":1,"ccw":3,"r":"one sentence reason"}}, ...]

Be strict: scores 9–10 should be rare. Most tech news is 3–6.
"""


def score_items(items: List[Dict]) -> List[Dict]:
    """
    Score all items using LLM. Takes top-40 by engagement, sends titles only.
    Items not in top-40 get ccw=0. Returns the same list with ccw/ccw_reason set.
    """
    # Init all items
    for item in items:
        item["ccw"]        = 0
        item["ccw_reason"] = ""

    if not items:
        return items

    # Pick top-40 by engagement score
    def _eng(item):
        try:
            return int(str(item.get("score") or item.get("stars") or 0).replace(",", "") or 0)
        except Exception:
            return 0

    top40 = sorted(items, key=_eng, reverse=True)[:40]

    # Build prompt — titles only
    lines = "\n".join(f"{i+1}. {item.get('title', '')}" for i, item in enumerate(top40))
    prompt = _CCW_PROMPT.format(items=lines)

    try:
        from core.rag_engine import llm
        from langchain_core.messages import HumanMessage

        response = llm.invoke([HumanMessage(content=prompt)])

        from core.token_tracker import track_response
        track_response(response, "ccw.score")

        # Extract JSON array from response
        m = _re.search(r'\[.*?\]', response.content, _re.DOTALL)
        if not m:
            return items

        results = _json.loads(m.group())
        for entry in results:
            idx = int(entry.get("i", 0)) - 1
            if 0 <= idx < len(top40):
                top40[idx]["ccw"]        = max(0, min(10, int(entry.get("ccw", 0))))
                top40[idx]["ccw_reason"] = str(entry.get("r", ""))[:200]

    except Exception as e:
        from core.error_logger import log_error
        log_error("ccw.score", "LLM batch scoring failed", str(e))

    return items


def ccw_label(score: int) -> str:
    """Return emoji+score label for display, empty string if score < 5."""
    if score >= 9:
        return f"🌍{score}"
    if score >= 7:
        return f"⚡{score}"
    if score >= 5:
        return f"💡{score}"
    return ""
