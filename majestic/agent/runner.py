"""Autonomous agent loop — smart alerts + daily ideas generator."""
from __future__ import annotations

import json
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from majestic.constants import MAJESTIC_HOME

_ALERTS_LOG = MAJESTIC_HOME / "alerts_log.json"
_notify_fn: Optional[Callable[[str], None]] = None

_SOURCE_TRUST: Dict[str, float] = {
    "hackernews": 1.0, "reddit": 0.9, "github_trending": 1.0,
    "newsapi": 1.0, "arxiv": 0.95, "google_trends": 0.8,
    "mastodon": 0.65, "devto": 0.6, "producthunt": 0.2,
}

ALERT_PROMPT = """You are a personal analyst. Strong signals were detected in fresh data.

Detected signals:
{signals}

Top items that triggered the alert:
{top_items}

Full context:
{context}

---

## 🚨 Signal Alert — {date}

**Why this matters:**
[2-3 sentences — what is happening and why significant. Reference actual signal sources.]

**What it means for you:**
[1-2 sentences — practical takeaway for a builder or investor]

**Recommended action:**
[One concrete action to take today]

**Sources:** [2-3 specific item titles from data]
"""


def set_notify(fn: Callable[[str], None]) -> None:
    global _notify_fn
    _notify_fn = fn


def _notify(text: str) -> None:
    if _notify_fn:
        try:
            _notify_fn(text)
        except Exception as e:
            print(f"[notify] error: {e}")
    else:
        print(f"[notify] {text}")


def _load_alerts() -> list:
    if _ALERTS_LOG.exists():
        try:
            return json.loads(_ALERTS_LOG.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_alerts(data: list) -> None:
    _ALERTS_LOG.parent.mkdir(parents=True, exist_ok=True)
    _ALERTS_LOG.write_text(json.dumps(data[-500:], ensure_ascii=False, indent=1), encoding="utf-8")


def _detect_signals(new_items: List[Dict]) -> Dict:
    if not new_items:
        return {"score": 0, "signals": [], "top_items": []}
    signals: list   = []
    top_items: list = []
    score           = 0

    words: Counter              = Counter()
    item_words: Dict[str, list] = {}
    for item in new_items:
        text = (item.get("title", "") + " " + (item.get("description") or "")).lower()
        src  = item.get("source", "")
        for w in [w for w in text.split() if len(w) > 4]:
            words[w] += 1
            item_words.setdefault(w, []).append(src)

    cross = {w: set(srcs) for w, srcs in item_words.items() if len(set(srcs)) >= 2 and words[w] >= 3}
    if cross:
        for w, srcs in sorted(cross.items(), key=lambda x: -len(x[1]))[:3]:
            signals.append(f"🔁 '{w}' across {len(srcs)} sources ({', '.join(srcs)})")
            score += 2

    for item in [i for i in new_items if i.get("source") == "github_trending"]:
        ns = item.get("new_stars", "")
        if ns:
            try:
                n = int(ns.replace(",", "").replace(" stars today", "").strip().split()[0])
                if n >= 300:
                    signals.append(f"⭐ GitHub spike: {item['title']} — {ns}")
                    top_items.append(item)
                    score += 3
            except Exception:
                pass

    hn_top = sorted([i for i in new_items if i.get("source") == "hackernews"], key=lambda x: x.get("score", 0), reverse=True)
    if hn_top and hn_top[0].get("score", 0) >= 300:
        signals.append(f"🔥 HN hit: '{hn_top[0]['title']}' — {hn_top[0]['score']} points")
        top_items.append(hn_top[0])
        score += 2

    reddit_top = sorted([i for i in new_items if i.get("source") == "reddit"], key=lambda x: x.get("score", 0), reverse=True)
    if reddit_top and reddit_top[0].get("score", 0) >= 1000:
        top = reddit_top[0]
        signals.append(f"📈 Reddit top: '{top['title']}' — {top['score']} in r/{top.get('subreddit','')}")
        top_items.append(top)
        score += 2

    if len(new_items) >= 60:
        signals.append(f"📊 High activity: {len(new_items)} new items")
        score += 1

    return {"score": score, "signals": signals, "top_items": top_items[:5]}


def check_and_alert(new_items: List[Dict], threshold: int = 7) -> Optional[str]:
    detection = _detect_signals(new_items)
    score     = detection["score"]
    signals   = detection["signals"]
    top_items = detection["top_items"]

    log = _load_alerts()
    log.append({"ts": datetime.now().isoformat(), "score": score, "sent": score >= threshold, "signals": signals})
    _save_alerts(log)

    if score < threshold or not signals:
        return None

    context = "\n".join(
        f"[{item.get('source','')}] {item.get('title','')}" + (f" — {(item.get('description') or item.get('selftext') or '')[:80]}" if item.get('description') or item.get('selftext') else "")
        for item in new_items[:40]
    )
    top_str = "\n".join(f"• [{i.get('source','')}] {i.get('title','')} (score: {i.get('score') or i.get('stars','')})" for i in top_items)
    prompt  = ALERT_PROMPT.format(signals="\n".join(signals), top_items=top_str, context=context[:4000], date=datetime.now().strftime("%d.%m.%Y %H:%M"))

    from majestic.config import get
    lang     = get("language", "EN")
    currency = get("currency", "USD")
    inst     = f"IMPORTANT: You MUST respond entirely in {lang}. Always use {currency} for monetary values."
    prompt   = f"{inst}\n\n{prompt}\n\n{inst}"

    try:
        from majestic.llm import get_provider
        from majestic.token_tracker import track
        resp = get_provider().complete([{"role": "user", "content": prompt}])
        try:
            um = resp.usage
            if um:
                track(um.input_tokens or 0, um.output_tokens or 0, "agent.smart_alert")
        except Exception:
            pass
        alert_text = resp.content
    except Exception as e:
        return f"Alert generation error: {e}"

    _notify(f"🚨 Smart Alert\n\n{alert_text}")
    return alert_text


_agent_started = False


def start_autonomous_agent(collect_fn, alert_threshold: int = 7, ideas_hour: int = 8) -> None:
    global _agent_started
    if _agent_started:
        return
    _agent_started = True

    def _loop():
        last_ideas_day = None
        while True:
            try:
                result    = collect_fn()
                new_items = result.get("new_items", [])
                if new_items:
                    check_and_alert(new_items, threshold=alert_threshold)
                now   = datetime.now()
                today = now.date()
                if now.hour >= ideas_hour and last_ideas_day != today:
                    last_ideas_day = today
                    from majestic.tools.research.ideas import _generate_ideas
                    ideas = _generate_ideas(force=False)
                    _notify(f"💡 Daily Ideas — {now.strftime('%Y-%m-%d')}\n\n{ideas}")
            except Exception as e:
                print(f"[Agent] error: {e}")
            time.sleep(6 * 3600)

    threading.Thread(target=_loop, daemon=True, name="autonomous-agent").start()
