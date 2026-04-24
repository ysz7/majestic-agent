"""
RSS feed manager — add/remove/list custom RSS feeds.
Feeds are stored in data/intel/rss_feeds.json.
Items are collected as part of the regular research cycle.
"""

import json
import requests
from datetime import datetime
from pathlib import Path
from typing import List, Dict

try:
    import feedparser
except ImportError:
    feedparser = None  # type: ignore

from core.intel import INTEL_DIR, HEADERS

RSS_FILE = INTEL_DIR / "rss_feeds.json"


# ── Storage ──────────────────────────────────────────────────────────────────

def _load() -> List[Dict]:
    if RSS_FILE.exists():
        try:
            return json.loads(RSS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save(feeds: List[Dict]):
    RSS_FILE.write_text(json.dumps(feeds, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Public API ───────────────────────────────────────────────────────────────

def list_feeds() -> List[Dict]:
    return _load()


def add_feed(url: str) -> Dict:
    """
    Add an RSS feed by URL. Fetches it once to validate and extract the title.
    Returns the saved feed entry.
    Raises ValueError if the feed is invalid or already exists.
    """
    if feedparser is None:
        raise RuntimeError("feedparser not installed — run: pip install feedparser")

    url = url.strip()
    feeds = _load()

    # Duplicate check
    if any(f["url"] == url for f in feeds):
        raise ValueError(f"Feed already exists: {url}")

    # Validate by fetching
    parsed = feedparser.parse(url)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"Could not parse RSS feed: {url}")

    title = parsed.feed.get("title") or url
    entry = {
        "url":   url,
        "name":  title[:80],
        "added": datetime.now().isoformat(timespec="seconds"),
    }
    feeds.append(entry)
    _save(feeds)
    return entry


def remove_feed(index: int) -> Dict:
    """
    Remove feed by 1-based index. Returns the removed entry.
    Raises IndexError if out of range.
    """
    feeds = _load()
    if index < 1 or index > len(feeds):
        raise IndexError(f"Invalid feed number: {index}. Use /rss list to see feeds.")
    removed = feeds.pop(index - 1)
    _save(feeds)
    return removed


# ── Fetcher ──────────────────────────────────────────────────────────────────

def fetch_all_feeds() -> List[Dict]:
    """Fetch all configured RSS feeds and return items in intel format."""
    if feedparser is None:
        print("[RSS] feedparser not installed — skipping")
        return []

    feeds = _load()
    if not feeds:
        return []

    results = []
    for feed in feeds:
        url  = feed["url"]
        name = feed["name"]
        try:
            parsed = feedparser.parse(url)
            for entry in parsed.entries[:20]:
                title = (entry.get("title") or "").strip()
                link  = entry.get("link") or entry.get("id") or ""
                desc  = (entry.get("summary") or entry.get("description") or "").strip()
                # Strip HTML tags from description
                if desc and "<" in desc:
                    from bs4 import BeautifulSoup
                    desc = BeautifulSoup(desc, "html.parser").get_text(strip=True)
                desc = desc[:300]
                if not title:
                    continue
                results.append({
                    "source":      "rss",
                    "feed_name":   name,
                    "title":       title,
                    "url":         link,
                    "description": desc,
                    "ts":          datetime.now().isoformat(),
                })
        except Exception as e:
            print(f"[RSS] {name}: {e}")
            from core.error_logger import log_error
            log_error("intel.rss", f"Failed to fetch feed: {name}", str(e))

    return results
