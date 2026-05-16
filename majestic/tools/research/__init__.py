"""
majestic.tools.research
~~~~~~~~~~~~~~~~~~~~~~~
Direct-fetch research tool — bypasses web search entirely.

Connects straight to curated RSS feeds and APIs, filters by query relevance,
and returns structured results sorted by date.  No search intermediary,
no rate-limit failures.

Sources are defined in sources.yaml next to this file — edit freely to add
or remove outlets.  Categories: news, tech, science, finance, ai.
"""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import httpx
import yaml

_SOURCES_FILE = Path(__file__).parent / "sources.yaml"

_TIMEOUT = httpx.Timeout(8.0, connect=4.0)
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Majestic-Research/1.0; RSS reader)"}

# Atom namespace
_ATOM_NS = "http://www.w3.org/2005/Atom"


# ── Source loader ─────────────────────────────────────────────────────────────

def load_sources() -> list[dict]:
    if not _SOURCES_FILE.exists():
        return []
    with _SOURCES_FILE.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("sources", [])


# ── Relevance ─────────────────────────────────────────────────────────────────

def _relevant(text: str, query: str) -> bool:
    """True when any meaningful query word appears in text."""
    words = [w.lower() for w in query.split() if len(w) > 2]
    if not words:
        return True
    tl = text.lower()
    return any(w in tl for w in words)


# ── Date parsing ──────────────────────────────────────────────────────────────

_DATE_FMTS = (
    "%a, %d %b %Y %H:%M:%S %z",
    "%a, %d %b %Y %H:%M:%S GMT",
    "%a, %d %b %Y %H:%M:%S +0000",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f%z",
)


def _parse_date(raw: str) -> str:
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw[:10] if raw else ""


# ── RSS / Atom fetcher ────────────────────────────────────────────────────────

def _text(el: ET.Element | None) -> str:
    if el is None:
        return ""
    return (el.text or "").strip()


async def _fetch_rss(client: httpx.AsyncClient, src: dict, query: str) -> list[dict]:
    try:
        r = await client.get(src["url"], headers=_HEADERS, timeout=_TIMEOUT,
                             follow_redirects=True)
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception:
        return []

    items: list[dict] = []
    name = src["name"]
    cat  = src.get("category", "general")

    # ── RSS 2.0  (<item> elements anywhere in the tree) ──────────────────────
    for item in root.findall(".//item"):
        title   = _text(item.find("title"))
        desc    = _text(item.find("description"))
        link    = _text(item.find("link"))
        pub     = _parse_date(_text(item.find("pubDate")))
        if not title:
            continue
        if not _relevant(title + " " + desc, query):
            continue
        # Strip HTML tags from description
        clean_desc = ET.fromstring(f"<x>{desc}</x>").itertext() if "<" in desc else iter([desc])
        summary = " ".join(clean_desc)[:220].strip()
        items.append({"source": name, "title": title, "summary": summary,
                      "url": link, "date": pub, "category": cat})

    # ── Atom  (<entry> elements) ──────────────────────────────────────────────
    if not items:
        ns = _ATOM_NS
        for entry in root.findall(f".//{{{ns}}}entry"):
            title   = _text(entry.find(f"{{{ns}}}title"))
            summary = _text(entry.find(f"{{{ns}}}summary"))
            if not summary:
                summary = _text(entry.find(f"{{{ns}}}content"))
            link_el = entry.find(f"{{{ns}}}link")
            link    = link_el.get("href", "") if link_el is not None else ""
            pub_raw = (_text(entry.find(f"{{{ns}}}published"))
                       or _text(entry.find(f"{{{ns}}}updated")))
            pub = _parse_date(pub_raw)
            if not title:
                continue
            if not _relevant(title + " " + summary, query):
                continue
            items.append({"source": name, "title": title,
                          "summary": summary[:220].strip(),
                          "url": link, "date": pub, "category": cat})

    return items[:6]


# ── Hacker News API ───────────────────────────────────────────────────────────

async def _fetch_hn(client: httpx.AsyncClient, src: dict, query: str) -> list[dict]:
    try:
        r = await client.get(src["url"], timeout=_TIMEOUT)
        ids: list[int] = r.json()[:40]
    except Exception:
        return []

    async def _item(sid: int) -> dict | None:
        try:
            resp = await client.get(
                f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                timeout=_TIMEOUT,
            )
            return resp.json()
        except Exception:
            return None

    raw_items = await asyncio.gather(*[_item(i) for i in ids[:20]])
    results: list[dict] = []
    for d in raw_items:
        if not d or d.get("type") != "story":
            continue
        title = d.get("title", "")
        if not title or not _relevant(title, query):
            continue
        url = d.get("url") or f"https://news.ycombinator.com/item?id={d['id']}"
        ts  = d.get("time", 0)
        date = datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else ""
        results.append({
            "source": "Hacker News",
            "title":   title,
            "summary": f"{d.get('score', 0)} pts · {d.get('descendants', 0)} comments",
            "url":     url,
            "date":    date,
            "category": "tech",
        })
        if len(results) >= 6:
            break
    return results


# ── Main research function ────────────────────────────────────────────────────

async def research(
    query: str,
    categories: str = "",
    max_results: int = 10,
) -> dict:
    """
    Research a topic by fetching directly from curated, verified sources.

    Connects to RSS feeds, APIs and known outlets without a search engine.
    Much faster and more reliable for current events, tech, science, finance.

    Args:
        query:       Topic or question to research.
        categories:  Comma-separated filter: news, tech, science, finance, ai
                     (empty = all categories).
        max_results: Maximum items to return (default 10).
    """
    sources = load_sources()
    if not sources:
        return {"error": "No sources configured. Edit majestic/tools/research/sources.yaml",
                "results": []}

    cats = {c.strip().lower() for c in categories.split(",") if c.strip()}
    if cats:
        sources = [s for s in sources if s.get("category", "general") in cats]

    async with httpx.AsyncClient() as client:
        tasks = [
            _fetch_hn(client, src, query) if src.get("type") == "hn_api"
            else _fetch_rss(client, src, query)
            for src in sources
        ]
        batches = await asyncio.gather(*tasks, return_exceptions=True)

    all_results: list[dict] = []
    ok: list[str] = []
    failed: list[str] = []

    for src, batch in zip(sources, batches):
        if isinstance(batch, Exception) or not isinstance(batch, list):
            failed.append(src["name"])
        elif batch:
            all_results.extend(batch)
            ok.append(src["name"])
        else:
            failed.append(src["name"])

    all_results.sort(key=lambda x: x.get("date", ""), reverse=True)

    return {
        "query":           query,
        "sources_ok":      ok,
        "sources_failed":  failed,
        "total":           len(all_results),
        "results":         all_results[:max_results],
    }
