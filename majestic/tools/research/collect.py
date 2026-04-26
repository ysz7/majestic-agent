"""Intel collection pipeline — dedup, CCW scoring, store to StateDB."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import List, Dict, Optional

from majestic.constants import MAJESTIC_HOME

_SEEN_FILE = MAJESTIC_HOME / "intel_seen_hashes.json"

_CCW_PROMPT = """You are evaluating news/tech items for their potential to change the world.

For each item assign a CCW score (0–10):
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

Be strict: scores 9-10 should be rare. Most tech news is 3-6."""


def _load_seen() -> set:
    if _SEEN_FILE.exists():
        try:
            return set(json.loads(_SEEN_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return set()


def _save_seen(seen: set) -> None:
    _SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SEEN_FILE.write_text(json.dumps(list(seen)[-10000:]), encoding="utf-8")


def _item_hash(title: str, url: str = "") -> str:
    return hashlib.md5((title.lower().strip() + url.strip()).encode()).hexdigest()


def score_items(items: List[Dict]) -> List[Dict]:
    for item in items:
        item["ccw"] = 0
        item["ccw_reason"] = ""
    if not items:
        return items

    def _eng(item):
        try:
            return int(str(item.get("score") or item.get("stars") or 0).replace(",", "") or 0)
        except Exception:
            return 0

    top40 = sorted(items, key=_eng, reverse=True)[:40]
    lines  = "\n".join(f"{i+1}. {item.get('title', '')}" for i, item in enumerate(top40))
    prompt = _CCW_PROMPT.format(items=lines)
    try:
        from majestic.llm import get_provider
        from majestic.token_tracker import track
        resp = get_provider().complete([{"role": "user", "content": prompt}])
        try:
            um = resp.usage
            if um:
                track(um.input_tokens or 0, um.output_tokens or 0, "ccw.score")
        except Exception:
            pass
        m = re.search(r'\[.*?\]', resp.content, re.DOTALL)
        if not m:
            return items
        for entry in json.loads(m.group()):
            idx = int(entry.get("i", 0)) - 1
            if 0 <= idx < len(top40):
                top40[idx]["ccw"]        = max(0, min(10, int(entry.get("ccw", 0))))
                top40[idx]["ccw_reason"] = str(entry.get("r", ""))[:200]
    except Exception:
        pass
    return items


def collect_and_index(on_progress=None) -> Dict:
    """Run all collectors, deduplicate, store new items to StateDB. Returns summary."""
    try:
        from filelock import FileLock
        _lock = FileLock(str(MAJESTIC_HOME / ".research.lock"), timeout=600)
    except ImportError:
        from contextlib import nullcontext
        _lock = nullcontext()

    with _lock:
        return _collect_inner(on_progress=on_progress)


def _collect_inner(on_progress=None) -> Dict:
    from majestic.tools.research.collectors import (
        fetch_hackernews, fetch_reddit, fetch_github_trending, fetch_producthunt,
    )
    from majestic.tools.research.collectors2 import (
        fetch_mastodon, fetch_devto, fetch_newsapi, fetch_arxiv, fetch_google_trends,
    )
    from majestic.tools.web.rss import list_feeds, fetch_all_feeds

    sources = [
        ("Hacker News",   lambda: fetch_hackernews(40)),
        ("Reddit",        fetch_reddit),
        ("GitHub",        lambda: fetch_github_trending("daily")),
        ("Product Hunt",  fetch_producthunt),
        ("Mastodon",      fetch_mastodon),
        ("Dev.to",        fetch_devto),
        ("Google Trends", fetch_google_trends),
        ("NewsAPI",       fetch_newsapi),
        ("arXiv",         fetch_arxiv),
    ]
    if list_feeds():
        sources.append(("RSS Feeds", fetch_all_feeds))

    import sys as _sys

    def _log(msg: str) -> None:
        _sys.stdout.write(msg + "\n")
        _sys.stdout.flush()

    seen      = _load_seen()
    all_items: List[Dict] = []
    total = len(sources)
    for i, (name, fn) in enumerate(sources, 1):
        if on_progress:
            on_progress(name, i, total)
            try:
                all_items += fn()
            except Exception:
                pass
        else:
            try:
                items = fn()
                all_items += items
                _log(f"├ {name} [{i}/{total}]")
            except Exception:
                _log(f"├ {name} [{i}/{total}]  [skip]")

    new_items = []
    for item in all_items:
        h = _item_hash(item.get("title", ""), item.get("url", ""))
        if h not in seen:
            seen.add(h)
            new_items.append(item)
    _save_seen(seen)

    if new_items:
        try:
            score_items(new_items)
        except Exception:
            pass
        try:
            from majestic.db.state import StateDB
            db = StateDB()
            db.add_news_items(new_items)
            _embed_news(db, new_items)
        except Exception:
            pass

    counts = {}
    for item in new_items:
        s = item.get("source", "unknown")
        counts[s] = counts.get(s, 0) + 1

    if not on_progress:
        _log(f"└ Done · {len(new_items)} new items")
    return {
        "total_new":  len(new_items),
        "total_seen": len(all_items) - len(new_items),
        "by_source":  counts,
        "timestamp":  datetime.now().isoformat(),
        "new_items":  new_items,
    }


def _embed_news(db, items: List[Dict]) -> None:
    """Embed news items into vector store grouped by source for semantic search."""
    from collections import defaultdict
    by_source: dict[str, list[str]] = defaultdict(list)
    for item in items:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        desc = (item.get("description") or item.get("selftext") or "").strip()[:300]
        text = f"[{item.get('source', 'news')}] {title}"
        if desc:
            text += f"\n{desc}"
        by_source[f"intel:{item.get('source', 'news')}"].append(text)
    for fname, texts in by_source.items():
        try:
            db.embed_and_store(fname, texts)
        except Exception:
            pass


def load_feed(source_filter: Optional[str] = None, limit: int = 100) -> List[Dict]:
    """Load recent news from StateDB."""
    try:
        from majestic.db.state import StateDB
        raw   = StateDB().load_news(limit=min(limit * 3, 3000) if source_filter else limit)
        items = []
        for row in raw:
            item = dict(row)
            if "collected_at" in item and "ts" not in item:
                item["ts"] = item["collected_at"]
            items.append(item)
        if source_filter:
            items = [i for i in items if i.get("source") == source_filter]
        return items[:limit]
    except Exception:
        return []
