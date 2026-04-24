"""
Smart Alerts — agent decides if something is worth notifying about
Idea Generator — 5 concrete business ideas per day

Smart Alert logic:
  After each data collection cycle the agent scores "importance" on a 1-10 scale.
  If >= 7 — sends Telegram notification. If < 7 — stays silent.

Importance criteria:
  - Topic mentioned 3+ times from different sources
  - GitHub repo gained anomalously many stars today
  - New technology/tool exploding simultaneously on HN + Reddit
  - Clear market opportunity with low competition
"""

import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Callable
from collections import Counter, defaultdict

from langchain_core.messages import HumanMessage
from core.rag_engine import llm
from core.intel import load_feed, INTEL_DIR

# ── Signal quality weights ───────────────────────────────────────────────────────
# Product Hunt = company marketing, NOT organic market signal
SOURCE_TRUST: Dict[str, float] = {
    "hackernews":      1.0,   # organic tech discussion
    "reddit":          0.9,   # community reaction
    "github_trending": 1.0,   # code actually being built
    "newsapi":         1.0,   # world news
    "arxiv":           0.95,  # research papers
    "google_trends":   0.8,   # consumer search interest
    "mastodon":        0.65,  # smaller community
    "devto":           0.6,   # mixed organic/promo
    "producthunt":     0.2,   # marketing launches — niche exists, demand NOT confirmed
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
    "tools", "using", "first", "large", "small", "data", "works", "work",
}

# Telegram notify hook — set by bot.py at startup via set_notify()
_notify_fn: Optional[Callable[[str], None]] = None


def set_notify(fn: Callable[[str], None]):
    """Register a callback that sends a Telegram message. Called by bot.py."""
    global _notify_fn
    _notify_fn = fn


def _notify(text: str):
    if _notify_fn:
        try:
            _notify_fn(text)
        except Exception as e:
            print(f"[notify] error: {e}")
    else:
        print(f"[notify] {text}")

ALERTS_LOG  = INTEL_DIR / "alerts_log.json"
IDEAS_LOG   = INTEL_DIR / "ideas_log.json"

# ── Helpers ─────────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> list:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_json(path: Path, data: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data[-500:], ensure_ascii=False, indent=1), encoding="utf-8")


# ── Signal detection (fast, no LLM) ─────────────────────────────────────────────

def _detect_signals(new_items: List[Dict]) -> Dict:
    """
    Quickly detect strong signals in new items without calling LLM.
    Returns {score: int, signals: list[str], top_items: list}
    """
    if not new_items:
        return {"score": 0, "signals": [], "top_items": []}

    signals   = []
    top_items = []
    score     = 0

    # 1. Cross-source topic clustering — same keyword in 3+ items from different sources
    words: Counter = Counter()
    item_words: Dict[str, list] = {}
    for item in new_items:
        text  = (item.get("title", "") + " " + (item.get("description") or "")).lower()
        src   = item.get("source", "")
        tokens = [w for w in text.split() if len(w) > 4]
        for w in tokens:
            words[w] += 1
            item_words.setdefault(w, []).append(src)

    # Find words appearing across multiple sources
    cross_source = {
        w: set(srcs) for w, srcs in item_words.items()
        if len(set(srcs)) >= 2 and words[w] >= 3
    }
    if cross_source:
        top_words = sorted(cross_source.items(), key=lambda x: -len(x[1]))[:3]
        for word, srcs in top_words:
            signals.append(f"🔁 '{word}' mentioned across {len(srcs)} sources simultaneously ({', '.join(srcs)})")
            score += 2

    # 2. GitHub stars spike — repos with unusually high new stars
    gh_items = [i for i in new_items if i.get("source") == "github_trending"]
    for item in gh_items:
        new_stars = item.get("new_stars", "")
        if new_stars:
            try:
                n = int(new_stars.replace(",", "").replace(" stars today", "").strip().split()[0])
                if n >= 300:
                    signals.append(f"⭐ GitHub spike: {item['title']} — {new_stars}")
                    top_items.append(item)
                    score += 3
            except Exception:
                pass

    # 3. High score HN items
    hn_items = sorted(
        [i for i in new_items if i.get("source") == "hackernews"],
        key=lambda x: x.get("score", 0), reverse=True
    )
    if hn_items and hn_items[0].get("score", 0) >= 300:
        top = hn_items[0]
        signals.append(f"🔥 HN hit: '{top['title']}' — {top['score']} points")
        top_items.append(top)
        score += 2

    # 4. Reddit high engagement
    reddit_items = sorted(
        [i for i in new_items if i.get("source") == "reddit"],
        key=lambda x: x.get("score", 0), reverse=True
    )
    if reddit_items and reddit_items[0].get("score", 0) >= 1000:
        top = reddit_items[0]
        signals.append(f"📈 Reddit top: '{top['title']}' — {top['score']} points in r/{top.get('subreddit','')}")
        top_items.append(top)
        score += 2

    # 5. Volume spike — many new items means active day
    if len(new_items) >= 60:
        signals.append(f"📊 High activity: {len(new_items)} new items this cycle")
        score += 1

    return {"score": score, "signals": signals, "top_items": top_items[:5]}


# ── Smart Alert ──────────────────────────────────────────────────────────────────

ALERT_PROMPT = """You are a personal analyst. Strong signals were detected in fresh data.

Detected signals (pre-scored by cross-source detection):
{signals}

Top items that triggered the alert:
{top_items}

Full context of new data:
{context}

---

Write a short alert message. Use this exact format:

## 🚨 Signal Alert — {date}

**Why this matters:**
[2–3 sentences — what is specifically happening and why it is significant. Reference the actual signal sources.]

**What it means for you:**
[1–2 sentences — practical takeaway for a builder or investor]

**Recommended action:**
[One concrete action to take today]

**Sources:** [list 2–3 specific item titles from the data above]

Be specific. No filler.
"""


def check_and_alert(new_items: List[Dict], threshold: int = 7) -> Optional[str]:
    """
    Analyze new items. If signal score >= threshold, generate and send alert email.
    Returns alert text if sent, None if nothing important.
    """
    detection = _detect_signals(new_items)
    score     = detection["score"]
    signals   = detection["signals"]
    top_items = detection["top_items"]

    # Log check
    log = _load_json(ALERTS_LOG)
    log.append({
        "ts":     datetime.now().isoformat(),
        "score":  score,
        "sent":   score >= threshold,
        "signals": signals,
    })
    _save_json(ALERTS_LOG, log)

    if score < threshold or not signals:
        print(f"[Alert] Score {score} < {threshold}, skipping.")
        return None

    # Build context for LLM
    context_lines = []
    for item in new_items[:40]:
        src   = item.get("source", "")
        title = item.get("title", "")
        desc  = (item.get("description") or item.get("selftext") or "")[:80]
        context_lines.append(f"[{src}] {title}" + (f" — {desc}" if desc else ""))
    context = "\n".join(context_lines)

    top_str = "\n".join(
        f"• [{i.get('source','')}] {i.get('title','')} (score: {i.get('score') or i.get('stars','')})"
        for i in top_items
    )

    prompt = ALERT_PROMPT.format(
        signals="\n".join(signals),
        top_items=top_str,
        context=context[:4000],
        date=datetime.now().strftime("%d.%m.%Y %H:%M"),
    )

    from core.config import get_lang, get_currency
    lang, currency = get_lang(), get_currency()
    _lang_inst = (
        f"IMPORTANT: You MUST respond entirely in {lang}. All text including section headers must be in {lang}. "
        f"Always use {currency} for all prices, costs, revenue estimates, and monetary values."
    )
    prompt = f"{_lang_inst}\n\n{prompt}\n\n{_lang_inst}"

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        from core.token_tracker import track_response
        track_response(response, "agent.smart_alert")
        alert_text = response.content
    except Exception as e:
        from core.error_logger import log_error
        log_error("agent.smart_alert", "LLM call failed", str(e))
        return f"❌ Alert generation error: {e}"

    _notify(f"🚨 Smart Alert\n\n{alert_text}")
    print(f"[Alert] Sent! Score={score}, signals={len(signals)}")
    return alert_text


def get_alerts_log(limit: int = 20) -> list:
    return list(reversed(_load_json(ALERTS_LOG)))[:limit]


# ── Idea Generator ───────────────────────────────────────────────────────────────

def _cluster_signals(items: List[Dict]) -> Dict[str, Dict]:
    """
    Group organic items by keyword topic cluster.
    Returns clusters confirmed by 2+ independent organic sources.
    Product Hunt is excluded from cluster confirmation (it's marketing).
    """
    organic = [i for i in items if SOURCE_TRUST.get(i.get("source", ""), 0.5) >= 0.6]

    word_to_sources: Dict[str, set] = defaultdict(set)
    word_to_items: Dict[str, list]  = defaultdict(list)

    for item in organic:
        title  = item.get("title", "")
        desc   = (item.get("description") or item.get("selftext") or "")
        text   = (title + " " + desc).lower()
        src    = item.get("source", "")
        tokens = {
            w.strip(".,!?:;()[]'\"") for w in text.split()
            if len(w) >= 5 and w.strip(".,!?:;()[]'\"") not in _STOP_WORDS
        }
        for w in tokens:
            word_to_sources[w].add(src)
            word_to_items[w].append(item)

    return {
        w: {"sources": srcs, "items": word_to_items[w], "strength": len(srcs)}
        for w, srcs in word_to_sources.items()
        if len(srcs) >= 2
    }


def _build_ideas_context(items: List[Dict]) -> str:
    """
    Build structured context for idea generation.
    Separates: CONFIRMED cross-source signals / single-source organic / Product Hunt promos.
    LLM sees clearly which signals are trustworthy.
    """
    clusters = _cluster_signals(items)

    # Assign each item to its strongest cluster (avoid duplication)
    item_best_cluster: Dict[str, str] = {}
    for w, data in sorted(clusters.items(), key=lambda x: -x[1]["strength"]):
        for item in data["items"]:
            title = item.get("title", "")
            if title not in item_best_cluster:
                item_best_cluster[title] = w

    # Build confirmed-signal lines grouped by cluster
    confirmed_lines: List[str] = []
    seen_confirmed: set = set()
    top_clusters = sorted(clusters.items(), key=lambda x: -x[1]["strength"])[:15]

    for w, data in top_clusters:
        cluster_added = 0
        for item in data["items"]:
            title = item.get("title", "")
            if title in seen_confirmed or item_best_cluster.get(title) != w:
                continue
            seen_confirmed.add(title)
            src      = item.get("source", "")
            score    = item.get("score") or item.get("stars") or ""
            desc     = (item.get("description") or item.get("selftext") or "")[:80]
            srcs_str = "+".join(sorted(data["sources"]))
            line     = f"[CONFIRMED:{srcs_str}] {title}"
            if desc:
                line += f" — {desc}"
            if score:
                line += f" ({score})"
            confirmed_lines.append(line)
            cluster_added += 1
            if cluster_added >= 3:
                break

    # Single-source organic items (weaker signal, listed for context)
    single_lines: List[str] = []
    seen_single = set(seen_confirmed)
    organic = [i for i in items if SOURCE_TRUST.get(i.get("source", ""), 0.5) >= 0.6]
    for item in organic[:40]:
        title = item.get("title", "")
        if title in seen_single:
            continue
        seen_single.add(title)
        src   = item.get("source", "")
        score = item.get("score") or item.get("stars") or ""
        desc  = (item.get("description") or item.get("selftext") or "")[:60]
        line  = f"[{src}] {title}"
        if desc:
            line += f" — {desc}"
        if score:
            line += f" ({score})"
        single_lines.append(line)

    # Product Hunt — listed separately, clearly marked as marketing
    ph_lines: List[str] = []
    for item in items:
        if item.get("source") == "producthunt":
            title = item.get("title", "")
            desc  = (item.get("description") or "")[:60]
            ph_lines.append(f"• {title}" + (f" — {desc}" if desc else ""))

    parts = []
    if confirmed_lines:
        parts.append(
            "=== CONFIRMED SIGNALS (2+ independent organic sources — HIGH CONFIDENCE) ===\n"
            + "\n".join(confirmed_lines[:30])
        )
    if single_lines:
        parts.append(
            "=== SINGLE-SOURCE SIGNALS (weaker — use only to support a CONFIRMED signal above) ===\n"
            + "\n".join(single_lines[:20])
        )
    if ph_lines:
        parts.append(
            "=== PRODUCT HUNT LAUNCHES (company marketing — niche EXISTS but demand NOT confirmed) ===\n"
            + "\n".join(ph_lines[:12])
        )

    return "\n\n".join(parts)


IDEAS_PROMPT = """You are a business idea generator for a solo entrepreneur.

Below are signals organized by reliability level:
- CONFIRMED signals appear across 2+ independent organic sources — these are real trends
- SINGLE-SOURCE signals may be noise — only use if they directly reinforce a CONFIRMED signal
- PRODUCT HUNT items are company marketing posts — niche exists but market demand is NOT confirmed

=== SIGNALS ===
{context}

---

STRICT VALIDATION RULES — follow exactly or the idea is invalid:

1. Every idea MUST be grounded in a CONFIRMED signal (2+ independent sources).
   If only a Product Hunt item supports the idea — the idea is INVALID. Reject it.

2. "Trend" field MUST cite specific confirmed items by name:
   e.g. "X trending on GitHub (1200 stars) + Y discussed on HN (450pts) + Z thread on r/..."
   A vague statement like "AI is trending" is NOT acceptable.

3. GitHub + HN + Reddit all covering the same topic = STRONG signal. Prioritize these.

4. A Product Hunt launch that then gets discussed on Reddit is ONE company's marketing
   reaching two platforms — NOT cross-niche confirmation. Do not treat it as confirmed.

5. An idea that is essentially "build the same thing someone just launched on Product Hunt"
   is INVALID unless that niche is also confirmed by 2+ organic sources independently.

Generate exactly 5 business ideas. Each must be:
- Buildable by one person in 2–6 weeks
- Grounded in CONFIRMED cross-source signals
- Have clear monetization

For each idea use this exact format:

### 💡 Idea N: [Name]

**Core:** [one sentence — what it is]
**Signal:** [MUST name specific confirmed items: source type + title + score/stars, minimum 2 independent sources]
**How to build:** [3 concrete steps]
**Monetization:** [how to earn and realistic numbers]
**Complexity:** [🟢 Low / 🟡 Medium / 🔴 High]
**Window:** [how long before this niche gets crowded]

---

After 5 ideas add:
### 🏆 Start with Idea N
[2 sentences — focus on signal strength and timing, not generic reasoning]
"""


def generate_ideas(force: bool = False) -> str:
    """
    Generate 5 business ideas based on today's intel.
    Generates once per day unless force=True.
    """
    # Check if already generated today
    if not force:
        log = _load_json(IDEAS_LOG)
        if log:
            last = log[-1]
            try:
                last_dt = datetime.fromisoformat(last["ts"])
                if (datetime.now() - last_dt).total_seconds() < 20 * 3600:
                    return last.get("ideas", "⚠️ Ideas already generated today. Use force=True to regenerate.")
            except Exception:
                pass

    # Build context from last 48h
    from core.intel import load_feed
    items = load_feed(limit=120)
    if not items:
        return "⚠️ No data for idea generation. Run /research first."

    context = _build_ideas_context(items)
    from core.config import get_lang, get_currency
    lang, currency = get_lang(), get_currency()
    _lang_inst = (
        f"IMPORTANT: You MUST respond entirely in {lang}. All text including section headers must be in {lang}. "
        f"Always use {currency} for all prices, costs, revenue estimates, and monetary values."
    )
    _raw_prompt = IDEAS_PROMPT.format(context=context[:6000])
    prompt  = f"{_lang_inst}\n\n{_raw_prompt}\n\n{_lang_inst}"

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        from core.token_tracker import track_response
        track_response(response, "agent.ideas")
        ideas    = response.content
    except Exception as e:
        from core.error_logger import log_error
        log_error("agent.ideas", "LLM call failed", str(e))
        return f"❌ Ideas generation error: {e}"

    # Save to log
    log = _load_json(IDEAS_LOG)
    log.append({"ts": datetime.now().isoformat(), "ideas": ideas})
    _save_json(IDEAS_LOG, log)

    # Save to exports
    out = Path(__file__).parent.parent / "data" / "exports" / f"ideas_{datetime.now().strftime('%Y%m%d')}.md"
    out.write_text(f"# 💡 Ideas — {datetime.now().strftime('%Y-%m-%d')}\n\n{ideas}", encoding="utf-8")

    return ideas


def get_ideas_history(limit: int = 7) -> list:
    """Return last N days of generated ideas."""
    return list(reversed(_load_json(IDEAS_LOG)))[:limit]


# ── Autonomous agent loop ────────────────────────────────────────────────────────

_agent_started = False


def start_autonomous_agent(
    collect_fn,               # core.intel.collect_and_index
    alert_threshold: int = 7,
    ideas_hour: int = 8,      # generate ideas at 8am
):
    """
    Background agent that:
    - After each collect cycle: checks signals and sends alert if important
    - Once per day at ideas_hour: generates 5 ideas and emails them
    """
    global _agent_started
    if _agent_started:
        return
    _agent_started = True

    def _loop():
        last_ideas_day = None

        while True:
            try:
                # ── Collect + Smart Alert ──────────────────────────────────
                result     = collect_fn()
                new_items  = result.get("new_items", [])

                if new_items:
                    alert = check_and_alert(new_items, threshold=alert_threshold)
                    if alert:
                        print(f"[Agent] Alert sent at {datetime.now().strftime('%H:%M')}")

                # ── Daily Ideas at configured hour ─────────────────────────
                now = datetime.now()
                today = now.date()
                if now.hour >= ideas_hour and last_ideas_day != today:
                    last_ideas_day = today
                    print("[Agent] Generating daily ideas...")
                    ideas = generate_ideas(force=False)
                    _notify(f"💡 Daily Ideas — {now.strftime('%Y-%m-%d')}\n\n{ideas}")
                    print("[Agent] Ideas notification sent.")

            except Exception as e:
                print(f"[Agent] error: {e}")

            time.sleep(6 * 3600)  # wait 6h then repeat

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    print("[Agent] Autonomous agent started.")
