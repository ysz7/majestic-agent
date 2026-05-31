"""
majestic.tools.research
~~~~~~~~~~~~~~~~~~~~~~~
Fetch from curated verified sources, deduplicate, and store to SQLite.

/research  — fetch all sources → store new articles → agent narrates briefing
/briefing  — analyze stored articles from last N days → investment signals
"""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

_SOURCES_FILE = Path(__file__).parent / "sources.yaml"
_TIMEOUT = httpx.Timeout(8.0, connect=4.0)
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Majestic-Research/1.0; RSS reader)"}
_ATOM_NS  = "http://www.w3.org/2005/Atom"


# ── Sources ───────────────────────────────────────────────────────────────────

def load_sources() -> list[dict]:
    if not _SOURCES_FILE.exists():
        return []
    with _SOURCES_FILE.open(encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("sources", [])


# ── Relevance & date ─────────────────────────────────────────────────────────

def _relevant(text: str, query: str) -> bool:
    if not query:
        return True
    words = [w.lower() for w in query.split() if len(w) > 2]
    tl = text.lower()
    return any(w in tl for w in words) if words else True


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


def _t(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None else ""


# ── Fetchers ──────────────────────────────────────────────────────────────────

async def _fetch_github_trending(client: httpx.AsyncClient, src: dict, query: str) -> list[dict]:
    from datetime import datetime, timedelta, timezone
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    try:
        r = await client.get(
            "https://api.github.com/search/repositories",
            params={"q": f"created:>{week_ago}", "sort": "stars", "order": "desc", "per_page": 10},
            headers={**_HEADERS, "Accept": "application/vnd.github.v3+json"},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []

    items = []
    for repo in data.get("items", []):
        name  = repo.get("full_name", "")
        desc  = (repo.get("description") or "")
        stars = repo.get("stargazers_count", 0)
        lang  = repo.get("language") or ""
        url   = repo.get("html_url", "")
        date  = (repo.get("created_at") or "")[:10]
        if not name or not _relevant(name + " " + desc, query):
            continue
        summary = f"★ {stars:,} stars"
        if lang:
            summary += f"  ·  {lang}"
        if desc:
            summary += f"  ·  {desc[:140]}"
        items.append({
            "source": src["name"],
            "title": name,
            "summary": summary[:240],
            "url": url,
            "date": date,
            "category": src.get("category", "tech"),
        })
    return items


async def _fetch_rss(client: httpx.AsyncClient, src: dict, query: str) -> list[dict]:
    try:
        r = await client.get(src["url"], headers=_HEADERS, timeout=_TIMEOUT,
                             follow_redirects=True)
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception:
        return []

    name = src["name"]
    cat  = src.get("category", "general")
    items: list[dict] = []

    # RSS 2.0
    for item in root.findall(".//item"):
        title = _t(item.find("title"))
        desc  = _t(item.find("description"))
        link  = _t(item.find("link"))
        pub   = _parse_date(_t(item.find("pubDate")))
        if not title or not _relevant(title + " " + desc, query):
            continue
        summary = desc[:240].replace("\n", " ").strip()
        items.append({"source": name, "title": title, "summary": summary,
                      "url": link, "date": pub, "category": cat})

    # Atom fallback
    if not items:
        for entry in root.findall(f".//{{{_ATOM_NS}}}entry"):
            title   = _t(entry.find(f"{{{_ATOM_NS}}}title"))
            summary = _t(entry.find(f"{{{_ATOM_NS}}}summary")) or \
                      _t(entry.find(f"{{{_ATOM_NS}}}content"))
            lel     = entry.find(f"{{{_ATOM_NS}}}link")
            link    = lel.get("href", "") if lel is not None else ""
            pub_raw = _t(entry.find(f"{{{_ATOM_NS}}}published")) or \
                      _t(entry.find(f"{{{_ATOM_NS}}}updated"))
            pub     = _parse_date(pub_raw)
            if not title or not _relevant(title + " " + summary, query):
                continue
            items.append({"source": name, "title": title,
                          "summary": summary[:240].strip(),
                          "url": link, "date": pub, "category": cat})

    return items[:20]


async def _fetch_hn(client: httpx.AsyncClient, src: dict, query: str) -> list[dict]:
    try:
        r = await client.get(src["url"], timeout=_TIMEOUT)
        ids: list[int] = r.json()[:40]
    except Exception:
        return []

    async def _item(sid: int) -> dict | None:
        try:
            return (await client.get(
                f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                timeout=_TIMEOUT)).json()
        except Exception:
            return None

    raw = await asyncio.gather(*[_item(i) for i in ids[:20]])
    results: list[dict] = []
    for d in raw:
        if not d or d.get("type") != "story":
            continue
        title = d.get("title", "")
        if not title or not _relevant(title, query):
            continue
        url  = d.get("url") or f"https://news.ycombinator.com/item?id={d['id']}"
        ts   = d.get("time", 0)
        date = datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else ""
        results.append({"source": "Hacker News", "title": title,
                        "summary": f"{d.get('score',0)} pts · {d.get('descendants',0)} comments",
                        "url": url, "date": date, "category": "tech"})
        if len(results) >= 20:
            break
    return results


# ── Main fetch function ───────────────────────────────────────────────────────

async def fetch_all(
    query: str = "",
    on_source=None,
) -> tuple[list[dict], list[dict], list[str]]:
    """Fetch all sources in parallel, reporting each as it completes.

    Returns (articles, ok_sources, failed_names).
    ok_sources: list of {"name": str, "count": int}
    on_source: optional sync callback(name: str, count: int, ok: bool)
               called immediately when each source responds.
    """
    sources = load_sources()

    async def _with_meta(client: httpx.AsyncClient, src: dict) -> tuple[dict, list]:
        t = src.get("type")
        if t == "hn_api":
            fn = _fetch_hn
        elif t == "github_trending":
            fn = _fetch_github_trending
        else:
            fn = _fetch_rss
        batch = await fn(client, src, query)
        return src, batch

    results: list[dict] = []
    ok: list[dict] = []
    failed: list[str] = []

    async with httpx.AsyncClient() as client:
        coros = [_with_meta(client, s) for s in sources]
        for task in asyncio.as_completed(coros):
            try:
                src, batch = await task
            except Exception:
                continue
            if isinstance(batch, list) and batch:
                results.extend(batch)
                ok.append({"name": src["name"], "count": len(batch)})
                if on_source:
                    on_source(src["name"], len(batch), True)
            else:
                failed.append(src["name"])
                if on_source:
                    on_source(src["name"], 0, False)

    results.sort(key=lambda x: x.get("date", ""), reverse=True)
    return results, ok, failed


# ── Tool callable (for agent) ─────────────────────────────────────────────────

async def research(query: str = "", max_results: int = 15) -> dict:
    """
    Fetch latest content from curated verified sources (RSS + APIs).

    Use this instead of web_search for current news, tech, science, finance, AI.
    Returns structured articles sorted by date — no search engine required.

    Args:
        query:       Optional topic filter (empty = all news).
        max_results: Maximum items to return.
    """
    articles, ok, failed = await fetch_all(query)
    return {
        "sources_ok":     [s["name"] for s in ok],
        "sources_failed": failed,
        "total":          len(articles),
        "results":        articles[:max_results],
    }
