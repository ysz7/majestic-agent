"""Intel collectors — HN, Reddit, GitHub, Product Hunt."""
from __future__ import annotations

import concurrent.futures
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Majestic-Agent/1.0 (personal research tool)",
    "Accept": "application/json, text/html",
}

_DEFAULT_REDDIT_SUBS = [
    "entrepreneur", "SideProject", "investing", "startups",
    "MachineLearning", "artificial", "programming", "technology",
    "business", "passive_income",
]


def _get_reddit_subs() -> list:
    import os
    raw = os.getenv("REDDIT_SUBS", "")
    if raw.strip():
        return [s.strip() for s in raw.split(",") if s.strip()]
    return _DEFAULT_REDDIT_SUBS


def fetch_hackernews(limit: int = 40) -> List[Dict]:
    def _fetch_item(eid):
        try:
            item = requests.get(
                f"https://hacker-news.firebaseio.com/v0/item/{eid}.json",
                headers=HEADERS, timeout=5
            ).json()
            if not item or item.get("type") != "story":
                return None
            return {
                "source":   "hackernews",
                "title":    item.get("title", ""),
                "url":      item.get("url", f"https://news.ycombinator.com/item?id={eid}"),
                "score":    item.get("score", 0),
                "comments": item.get("descendants", 0),
                "by":       item.get("by", ""),
                "ts":       datetime.now().isoformat(),
            }
        except Exception:
            return None

    try:
        resp = requests.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json",
            headers=HEADERS, timeout=10
        )
        ids = resp.json()[:limit]
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            futures = {ex.submit(_fetch_item, eid): eid for eid in ids}
            results = []
            for f in concurrent.futures.as_completed(futures, timeout=30):
                item = f.result()
                if item:
                    results.append(item)
        return results
    except Exception as e:
        print(f"[HN] error: {e}")
        return []


def fetch_reddit(subreddits: List[str] = None, limit_per_sub: int = 15) -> List[Dict]:
    subs    = subreddits or _get_reddit_subs()
    results = []
    session = requests.Session()
    session.headers.update(HEADERS)
    for sub in subs:
        try:
            resp = session.get(f"https://www.reddit.com/r/{sub}/hot.json?limit={limit_per_sub}", timeout=8)
            if resp.status_code != 200:
                continue
            for post in resp.json().get("data", {}).get("children", []):
                p = post.get("data", {})
                if p.get("stickied") or p.get("is_video"):
                    continue
                results.append({
                    "source":    "reddit",
                    "subreddit": sub,
                    "title":     p.get("title", ""),
                    "url":       p.get("url", ""),
                    "score":     p.get("score", 0),
                    "comments":  p.get("num_comments", 0),
                    "selftext":  (p.get("selftext") or "")[:500],
                    "ts":        datetime.now().isoformat(),
                })
            time.sleep(0.5)
        except Exception as e:
            print(f"[Reddit] r/{sub} error: {e}")
    return results


def fetch_github_trending(period: str = "daily") -> List[Dict]:
    results  = []
    _headers = {**HEADERS, "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
    try:
        resp     = requests.get(f"https://github.com/trending?since={period}", headers=_headers, timeout=12)
        soup     = BeautifulSoup(resp.text, "html.parser")
        articles = soup.select("article.Box-row") or soup.select("article")
        for art in articles[:30]:
            try:
                name_tag = art.select_one("h2 a") or art.select_one("h1 a")
                if not name_tag:
                    continue
                repo_path = name_tag.get("href", "").strip("/")
                if not repo_path or "/" not in repo_path:
                    continue
                stars_link = art.select_one("a[href$='/stargazers']")
                today_span = art.select_one("span.d-inline-block.float-sm-right")
                desc_tag   = art.select_one("p")
                lang_tag   = art.select_one("span[itemprop='programmingLanguage']")
                results.append({
                    "source":      "github_trending",
                    "title":       repo_path,
                    "url":         f"https://github.com/{repo_path}",
                    "description": desc_tag.get_text(strip=True) if desc_tag else "",
                    "language":    lang_tag.get_text(strip=True) if lang_tag else "",
                    "stars":       stars_link.get_text(strip=True).replace(",", "") if stars_link else "0",
                    "new_stars":   today_span.get_text(strip=True) if today_span else "",
                    "period":      period,
                    "ts":          datetime.now().isoformat(),
                })
            except Exception:
                continue
    except Exception as e:
        print(f"[GitHub] error: {e}")
    return results


def fetch_producthunt() -> List[Dict]:
    return _fetch_ph_rss() or _fetch_ph_scrape()


def _fetch_ph_rss() -> List[Dict]:
    _hdr = {**HEADERS,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
            "Accept": "application/rss+xml, application/xml, text/xml, */*"}
    try:
        resp = requests.get("https://www.producthunt.com/feed", headers=_hdr, timeout=10)
        if resp.status_code != 200:
            return []
        text = resp.text.strip()
        if not text.startswith("<") or "<html" in text[:200].lower():
            return []
        channel = ET.fromstring(text).find("channel")
        if not channel:
            return []
        results = []
        for item in channel.findall("item")[:25]:
            title = (item.findtext("title") or "").strip()
            if not title:
                continue
            results.append({
                "source":      "producthunt",
                "title":       title,
                "url":         (item.findtext("link") or "").strip(),
                "description": BeautifulSoup((item.findtext("description") or "")[:400], "html.parser").get_text(strip=True)[:300],
                "ts":          datetime.now().isoformat(),
            })
        return results
    except Exception as e:
        print(f"[ProductHunt RSS] {e}")
        return []


def _fetch_ph_scrape() -> List[Dict]:
    _hdr = {**HEADERS,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml"}
    try:
        resp = requests.get("https://www.producthunt.com/", headers=_hdr, timeout=12)
        if resp.status_code != 200:
            return []
        soup        = BeautifulSoup(resp.text, "html.parser")
        results     = []
        seen_titles: set = set()
        for a in soup.select("a[href*='/posts/']"):
            title = a.get_text(strip=True)
            href  = a.get("href", "")
            if not title or len(title) < 4 or title in seen_titles or href.count("/") < 2:
                continue
            seen_titles.add(title)
            url    = f"https://www.producthunt.com{href}" if href.startswith("/") else href
            parent = a.parent
            desc   = ""
            if parent:
                sib = parent.find_next_sibling()
                if sib:
                    desc = sib.get_text(strip=True)[:200]
            results.append({"source": "producthunt", "title": title, "url": url, "description": desc, "ts": datetime.now().isoformat()})
            if len(results) >= 20:
                break
        return results
    except Exception as e:
        print(f"[ProductHunt scrape] {e}")
        return []
