"""Intel collectors — Mastodon, Dev.to, NewsAPI, arXiv, Google Trends."""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Majestic-Agent/1.0 (personal research tool)",
    "Accept": "application/json, text/html",
}


def fetch_mastodon(limit: int = 20) -> List[Dict]:
    instance = os.getenv("MASTODON_INSTANCE", "mastodon.social").rstrip("/")
    _hdr     = {**HEADERS, "User-Agent": "Mozilla/5.0 (compatible; Majestic-Agent/1.0)"}
    results  = []
    try:
        resp = requests.get(
            f"https://{instance}/api/v1/trends/statuses?limit={limit}",
            headers=_hdr, timeout=10,
        )
        if resp.status_code != 200:
            return []
        for post in resp.json():
            content = BeautifulSoup(post.get("content", ""), "html.parser").get_text(strip=True)
            if not content:
                continue
            results.append({
                "source":      "mastodon",
                "title":       content[:120],
                "url":         post.get("url", ""),
                "description": content[:300],
                "score":       post.get("favourites_count", 0) + post.get("reblogs_count", 0),
                "by":          post.get("account", {}).get("acct", ""),
                "ts":          datetime.now().isoformat(),
            })
    except Exception as e:
        print(f"[Mastodon] error: {e}")
    return results


def fetch_devto(top_days: int = 3, limit: int = 30) -> List[Dict]:
    _hdr    = {**HEADERS}
    api_key = os.getenv("DEVTO_API_KEY", "")
    if api_key:
        _hdr["api-key"] = api_key
    results = []
    try:
        resp = requests.get(
            f"https://dev.to/api/articles?top={top_days}&per_page={limit}",
            headers=_hdr, timeout=10,
        )
        if resp.status_code != 200:
            return []
        for art in resp.json():
            title = (art.get("title") or "").strip()
            if not title:
                continue
            tags  = ", ".join(art.get("tag_list") or [])
            desc  = (art.get("description") or "").strip()[:300]
            results.append({
                "source":      "devto",
                "title":       title,
                "url":         art.get("url") or art.get("canonical_url") or "",
                "description": f"{desc} [tags: {tags}]" if tags else desc,
                "score":       art.get("public_reactions_count", 0) + art.get("comments_count", 0),
                "ts":          datetime.now().isoformat(),
            })
    except Exception as e:
        print(f"[Dev.to] error: {e}")
    return results


def fetch_newsapi(limit_per_category: int = 10) -> List[Dict]:
    api_key = os.getenv("NEWSAPI_KEY", "")
    if not api_key:
        return []
    results   = []
    seen_urls: set = set()
    for category in ["technology", "business", "science", "general"]:
        try:
            resp = requests.get(
                "https://newsapi.org/v2/top-headlines",
                params={"category": category, "pageSize": limit_per_category, "language": "en", "apiKey": api_key},
                headers=HEADERS, timeout=10,
            )
            data = resp.json()
            if resp.status_code == 429 or data.get("code") == "rateLimited":
                break
            if resp.status_code != 200 or data.get("status") != "ok":
                continue
            for article in data.get("articles", []):
                title = (article.get("title") or "").strip()
                url   = (article.get("url") or "").strip()
                if not title or url in seen_urls or "[Removed]" in title:
                    continue
                seen_urls.add(url)
                source_name = (article.get("source") or {}).get("name", "")
                desc        = (article.get("description") or "").strip()[:400]
                results.append({
                    "source":      "newsapi",
                    "category":    category,
                    "title":       title,
                    "url":         url,
                    "description": f"[{source_name}] {desc}" if source_name else desc,
                    "ts":          datetime.now().isoformat(),
                })
        except Exception as e:
            print(f"[NewsAPI] {category} error: {e}")
    return results


def fetch_arxiv(max_results: int = 30) -> List[Dict]:
    search_query = "cat:cs.AI OR cat:cs.LG OR cat:cs.CL OR cat:econ.GN OR cat:q-fin.ST"
    results      = []
    try:
        resp = requests.get(
            "http://export.arxiv.org/api/query",
            params={"search_query": search_query, "sortBy": "submittedDate",
                    "sortOrder": "descending", "max_results": max_results},
            headers=HEADERS, timeout=15,
        )
        if resp.status_code != 200:
            return []
        ns   = {"atom": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(resp.text)
        for entry in root.findall("atom:entry", ns):
            title   = (entry.findtext("atom:title", "", ns) or "").strip().replace("\n", " ")
            summary = (entry.findtext("atom:summary", "", ns) or "").strip().replace("\n", " ")[:400]
            url     = (entry.findtext("atom:id", "", ns) or "").strip()
            cats    = ", ".join(c.get("term", "") for c in entry.findall("atom:category", ns) if c.get("term"))
            if not title or not url:
                continue
            results.append({
                "source":      "arxiv",
                "title":       title,
                "url":         url,
                "description": f"[{cats}] {summary}" if cats else summary,
                "ts":          datetime.now().isoformat(),
            })
    except Exception as e:
        print(f"[arXiv] error: {e}")
    return results


def fetch_google_trends(limit: int = 20) -> List[Dict]:
    import concurrent.futures
    try:
        from pytrends.request import TrendReq
    except ImportError:
        return []
    geo    = os.getenv("GOOGLE_TRENDS_GEO", "US")
    pn_map = {
        "US": "united_states", "GB": "united_kingdom", "DE": "germany",
        "UA": "ukraine", "PL": "poland", "FR": "france",
        "CA": "canada", "AU": "australia", "IN": "india",
    }
    pn = pn_map.get(geo.upper(), "united_states")

    def _fetch():
        pt = TrendReq(hl="en-US", tz=0, timeout=(8, 10))
        return pt.trending_searches(pn=pn)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            df = ex.submit(_fetch).result(timeout=15)
        results = []
        for term in df[0].head(limit).tolist():
            term = str(term).strip()
            if not term:
                continue
            results.append({
                "source":      "google_trends",
                "title":       term,
                "url":         f"https://trends.google.com/trends/explore?q={requests.utils.quote(term)}&geo={geo}",
                "description": f"Trending search in {geo}",
                "ts":          datetime.now().isoformat(),
            })
        return results
    except concurrent.futures.TimeoutError:
        print("[Google Trends] timeout — rate-limited, skipping")
        return []
    except Exception as e:
        print(f"[Google Trends] error: {e}")
        return []
