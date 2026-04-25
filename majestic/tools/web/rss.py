"""RSS feed management — stored in MAJESTIC_HOME/rss_feeds.json."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from majestic.constants import MAJESTIC_HOME

_FILE = MAJESTIC_HOME / "rss_feeds.json"
_HEADERS = {"User-Agent": "Majestic-Agent/1.0"}


def _load() -> list:
    if _FILE.exists():
        try:
            return json.loads(_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save(feeds: list) -> None:
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    _FILE.write_text(json.dumps(feeds, indent=2, ensure_ascii=False), encoding="utf-8")


def list_feeds() -> list:
    return _load()


def add_feed(url: str) -> dict:
    try:
        import feedparser
    except ImportError:
        raise RuntimeError("feedparser not installed")
    url = url.strip()
    feeds = _load()
    if any(f["url"] == url for f in feeds):
        raise ValueError(f"Feed already exists: {url}")
    parsed = feedparser.parse(url)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"Could not parse RSS feed: {url}")
    entry = {"url": url, "name": (parsed.feed.get("title") or url)[:80],
             "added": datetime.now().isoformat(timespec="seconds")}
    feeds.append(entry)
    _save(feeds)
    return entry


def remove_feed(index: int) -> dict:
    feeds = _load()
    if index < 1 or index > len(feeds):
        raise IndexError(f"Invalid feed number: {index}")
    removed = feeds.pop(index - 1)
    _save(feeds)
    return removed


def fetch_all_feeds() -> list:
    """Fetch all configured RSS feeds and return items in intel format."""
    try:
        import feedparser
    except ImportError:
        return []
    results = []
    for feed in _load():
        url = feed["url"]
        try:
            parsed = feedparser.parse(url)
            for entry in parsed.entries[:20]:
                title = (entry.get("title") or "").strip()
                if not title:
                    continue
                desc = (entry.get("summary") or entry.get("description") or "").strip()
                if desc and "<" in desc:
                    try:
                        from bs4 import BeautifulSoup
                        desc = BeautifulSoup(desc, "html.parser").get_text(strip=True)
                    except Exception:
                        pass
                results.append({
                    "source": "rss",
                    "feed_name": feed["name"],
                    "title": title,
                    "url": entry.get("link") or entry.get("id") or "",
                    "description": desc[:300],
                    "ts": datetime.now().isoformat(),
                })
        except Exception as e:
            print(f"[RSS] {feed['name']}: {e}")
    return results
