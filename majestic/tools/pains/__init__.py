"""
majestic.tools.pains
~~~~~~~~~~~~~~~~~~~~
Fetch pain-signal community sources, batch-extract user pain points via LLM.

/pains   — fetch → store raw posts → LLM extract → immediate summary
/briefing — PAIN RADAR (section 5) + 5 IDEAS FROM PAIN (section 6)
"""

from __future__ import annotations

import asyncio
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import httpx
import yaml

_SOURCES_FILE = Path(__file__).parent / "sources.yaml"
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Majestic-Research/1.0; RSS reader)"}
_ATOM_NS = "http://www.w3.org/2005/Atom"


def load_sources() -> list[dict]:
    if not _SOURCES_FILE.exists():
        return []
    with _SOURCES_FILE.open(encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("sources", [])


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


async def _fetch_rss(client: httpx.AsyncClient, src: dict) -> list[dict]:
    try:
        r = await client.get(src["url"], headers=_HEADERS, timeout=_TIMEOUT,
                             follow_redirects=True)
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception:
        return []

    name = src["name"]
    items: list[dict] = []

    for item in root.findall(".//item"):
        title = _t(item.find("title"))
        desc  = _t(item.find("description"))
        link  = _t(item.find("link"))
        pub   = _parse_date(_t(item.find("pubDate")))
        if not title:
            continue
        items.append({"source": name, "title": title,
                      "summary": desc[:300].replace("\n", " ").strip(),
                      "url": link, "date": pub})

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
            if not title:
                continue
            items.append({"source": name, "title": title,
                          "summary": summary[:300].strip(),
                          "url": link, "date": pub})

    return items[:25]


async def _fetch_hn_ask(client: httpx.AsyncClient, src: dict) -> list[dict]:
    try:
        r = await client.get(src["url"], timeout=_TIMEOUT)
        ids: list[int] = r.json()[:30]
    except Exception:
        return []

    async def _item(sid: int) -> dict | None:
        try:
            return (await client.get(
                f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                timeout=_TIMEOUT,
            )).json()
        except Exception:
            return None

    raw = await asyncio.gather(*[_item(i) for i in ids[:20]])
    results: list[dict] = []
    for d in raw:
        if not d or d.get("type") != "story":
            continue
        title = d.get("title", "")
        if not title:
            continue
        url      = d.get("url") or f"https://news.ycombinator.com/item?id={d['id']}"
        ts       = d.get("time", 0)
        date_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else ""
        body     = (d.get("text") or "")[:300].replace("\n", " ").strip()
        results.append({"source": "HN Ask", "title": title,
                        "summary": body, "url": url, "date": date_str})
    return results


async def fetch_all(on_source=None) -> tuple[list[dict], list[dict], list[str]]:
    """Fetch all pain-signal sources in parallel. Returns (posts, ok_sources, failed_names)."""
    sources = load_sources()

    async def _with_meta(client: httpx.AsyncClient, src: dict) -> tuple[dict, list]:
        if src.get("type") == "hn_ask":
            batch = await _fetch_hn_ask(client, src)
        else:
            batch = await _fetch_rss(client, src)
        return src, batch

    results: list[dict] = []
    ok: list[dict]      = []
    failed: list[str]   = []

    async with httpx.AsyncClient() as client:
        coros = [_with_meta(client, s) for s in sources]
        for task in asyncio.as_completed(coros):
            try:
                src, batch = await task
            except Exception:
                continue
            name = src.get("name", "?") if isinstance(src, dict) else "?"
            if isinstance(batch, list) and batch:
                results.extend(batch)
                ok.append({"name": name, "count": len(batch)})
                if on_source:
                    on_source(name, len(batch), True)
            else:
                failed.append(name)
                if on_source:
                    on_source(name, 0, False)

    results.sort(key=lambda x: x.get("date", ""), reverse=True)
    return results, ok, failed


async def extract_pains(posts: list[dict], llm, lang: str = "en") -> list[dict]:
    """
    One LLM call over up to 60 posts. Returns [{pain_text, domain, source, url, date}].
    domain values: b2b, devtools, marketing, productivity, design, finance, hr, other
    lang: language code for pain_text output (e.g. "ru", "en")
    """
    if not posts:
        return []

    _lang_rule = (
        f"Write each 'pain' value in {lang}. "
        if lang and lang.lower() not in ("en", "english") else ""
    )
    lines = [
        "Extract real user pain points from these community posts.\n"
        f"Rules: only genuine expressed frustrations or unsolved problems. Skip promotions. {_lang_rule}\n"
        "Domain values: b2b, devtools, marketing, productivity, design, finance, hr, other\n\n"
        "Return ONLY a JSON array — no commentary, no markdown fences:\n"
        '[{"pain": "concise pain description", "domain": "...", "idx": N}, ...]\n\n'
        "Posts:\n"
    ]
    for i, p in enumerate(posts[:60]):
        lines.append(f"[{i}] {p['source']} — {p['title']}")
        if p.get("summary"):
            lines.append(f"    {p['summary'][:150]}")

    messages = [
        {"role": "system",
         "content": "Pain point extraction engine. Return ONLY a valid JSON array, nothing else."},
        {"role": "user", "content": "\n".join(lines)},
    ]

    try:
        response = await llm.chat(messages, step_type="simple")
        content  = response.get("content", "")
        m = re.search(r'\[.*\]', content, re.DOTALL)
        if not m:
            return []
        extracted = json.loads(m.group())
        pains = []
        for item in extracted:
            idx  = item.get("idx", 0)
            post = posts[idx] if 0 <= idx < len(posts) else {}
            pain_text = item.get("pain", "").strip()
            if not pain_text:
                continue
            pains.append({
                "pain_text": pain_text,
                "domain":    item.get("domain", "other"),
                "source":    post.get("source", ""),
                "url":       post.get("url", ""),
                "date":      post.get("date", ""),
            })
        return pains
    except Exception:
        return []
