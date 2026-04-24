"""
Web Intelligence — data collector from open sources
- Hacker News (official API)
- Reddit (JSON API, no keys)
- GitHub Trending (HTML scraping)
- Deduplication via MD5 hashes
- Background scheduler every 6 hours
"""

import json
import time
import hashlib
import threading
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from bs4 import BeautifulSoup

# ── Paths ───────────────────────────────────────────────────────────────────────
INTEL_DIR  = Path(__file__).parent.parent / "data" / "intel"
SEEN_FILE  = INTEL_DIR / "seen_hashes.json"
FEED_FILE  = INTEL_DIR / "latest_feed.json"
INTEL_DIR.mkdir(parents=True, exist_ok=True)

# Cross-process lock — works between CLI and bot, including separate Docker containers
# sharing the same data/ volume. Lock file lives in data/intel/.
_RESEARCH_LOCK = INTEL_DIR / ".research.lock"

HEADERS = {
    "User-Agent": "Parallax/1.0 (personal research tool)",
    "Accept": "application/json, text/html",
}

# Default subreddits — override via REDDIT_SUBS in .env (comma-separated)
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

# ── Seen hashes (dedup) ─────────────────────────────────────────────────────────

def _load_seen() -> set:
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text()))
        except Exception:
            return set()
    return set()


def _save_seen(seen: set):
    # Keep only last 10k hashes to avoid bloat
    lst = list(seen)[-10000:]
    SEEN_FILE.write_text(json.dumps(lst), encoding="utf-8")


def _item_hash(title: str, url: str = "") -> str:
    raw = (title.lower().strip() + url.strip())
    return hashlib.md5(raw.encode()).hexdigest()


def _is_duplicate(title: str, url: str, seen: set) -> bool:
    return _item_hash(title, url) in seen


# ── Hacker News ─────────────────────────────────────────────────────────────────

def fetch_hackernews(limit: int = 40) -> List[Dict]:
    """Fetch top stories from Hacker News API (parallel requests)."""
    import concurrent.futures

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


# ── Reddit ───────────────────────────────────────────────────────────────────────

def fetch_reddit(subreddits: List[str] = None, limit_per_sub: int = 15) -> List[Dict]:
    """Fetch hot posts from Reddit using public JSON API (no auth needed)."""
    subs = subreddits or _get_reddit_subs()
    results = []
    session = requests.Session()
    session.headers.update(HEADERS)

    for sub in subs:
        try:
            url = f"https://www.reddit.com/r/{sub}/hot.json?limit={limit_per_sub}"
            resp = session.get(url, timeout=8)
            if resp.status_code != 200:
                continue
            data = resp.json()
            posts = data.get("data", {}).get("children", [])
            for post in posts:
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
            time.sleep(0.5)  # be polite to Reddit
        except Exception as e:
            print(f"[Reddit] r/{sub} error: {e}")
            continue
    return results


# ── GitHub Trending ──────────────────────────────────────────────────────────────

def fetch_github_trending(period: str = "daily") -> List[Dict]:
    """Scrape GitHub trending page."""
    results = []
    url = f"https://github.com/trending?since={period}"
    _headers = {**HEADERS, "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
    try:
        resp = requests.get(url, headers=_headers, timeout=12)
        soup = BeautifulSoup(resp.text, "html.parser")
        # GitHub uses article.Box-row; fallback to any article
        articles = soup.select("article.Box-row") or soup.select("article")
        for art in articles[:30]:
            try:
                # Repo name: <h2> or <h1> link
                name_tag = art.select_one("h2 a") or art.select_one("h1 a")
                if not name_tag:
                    continue
                repo_path = name_tag.get("href", "").strip("/")
                if not repo_path or "/" not in repo_path:
                    continue
                repo_url = f"https://github.com/{repo_path}"

                desc_tag = art.select_one("p")
                desc = desc_tag.get_text(strip=True) if desc_tag else ""

                # Stars: link to /stargazers is most reliable
                stars_link = art.select_one("a[href$='/stargazers']")
                stars = stars_link.get_text(strip=True).replace(",", "") if stars_link else "0"

                # Stars today: last <span> in the float-right block
                today_span = art.select_one("span.d-inline-block.float-sm-right")
                new_stars = today_span.get_text(strip=True) if today_span else ""

                lang_tag = art.select_one("span[itemprop='programmingLanguage']")
                lang = lang_tag.get_text(strip=True) if lang_tag else ""

                results.append({
                    "source":      "github_trending",
                    "title":       repo_path,
                    "url":         repo_url,
                    "description": desc,
                    "language":    lang,
                    "stars":       stars,
                    "new_stars":   new_stars,
                    "period":      period,
                    "ts":          datetime.now().isoformat(),
                })
            except Exception:
                continue
        if not results:
            print(f"[GitHub] parsed 0 repos — page structure may have changed")
    except Exception as e:
        print(f"[GitHub] error: {e}")
    return results


# ── Product Hunt ─────────────────────────────────────────────────────────────────

def fetch_producthunt() -> List[Dict]:
    """
    Fetch Product Hunt via RSS feed with browser UA.
    Falls back to scraping the homepage if RSS returns HTML/fails.
    """
    results = _fetch_ph_rss()
    if not results:
        results = _fetch_ph_scrape()
    return results


def _fetch_ph_rss() -> List[Dict]:
    import xml.etree.ElementTree as ET
    _headers = {**HEADERS,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
                "Accept": "application/rss+xml, application/xml, text/xml, */*"}
    try:
        resp = requests.get("https://www.producthunt.com/feed", headers=_headers, timeout=10)
        if resp.status_code != 200:
            return []
        # Guard: PH sometimes returns HTML redirect instead of XML
        text = resp.text.strip()
        if not text.startswith("<") or "<html" in text[:200].lower():
            return []
        root = ET.fromstring(text)
        channel = root.find("channel")
        if not channel:
            return []
        results = []
        for item in channel.findall("item")[:25]:
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link") or "").strip()
            desc  = (item.findtext("description") or "").strip()[:400]
            # Strip HTML tags from description
            desc = BeautifulSoup(desc, "html.parser").get_text(strip=True)[:300]
            if not title:
                continue
            results.append({
                "source":      "producthunt",
                "title":       title,
                "url":         link,
                "description": desc,
                "ts":          datetime.now().isoformat(),
            })
        return results
    except Exception as e:
        print(f"[ProductHunt RSS] {e}")
        return []


def _fetch_ph_scrape() -> List[Dict]:
    """Scrape Product Hunt homepage as fallback."""
    _headers = {**HEADERS,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml"}
    try:
        resp = requests.get("https://www.producthunt.com/", headers=_headers, timeout=12)
        if resp.status_code != 200:
            print(f"[ProductHunt scrape] HTTP {resp.status_code}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        # PH cards have data-test="post-item" or similar; title links point to /posts/
        seen_titles: set = set()
        for a in soup.select("a[href*='/posts/']"):
            title = a.get_text(strip=True)
            href  = a.get("href", "")
            if not title or len(title) < 4 or title in seen_titles:
                continue
            # Skip nav/footer links (very short paths like /posts without slug)
            if href.count("/") < 2:
                continue
            seen_titles.add(title)
            url = f"https://www.producthunt.com{href}" if href.startswith("/") else href
            # Try to find a sibling tagline
            parent = a.parent
            desc = ""
            if parent:
                tagline = parent.find_next_sibling()
                if tagline:
                    desc = tagline.get_text(strip=True)[:200]
            results.append({
                "source":      "producthunt",
                "title":       title,
                "url":         url,
                "description": desc,
                "ts":          datetime.now().isoformat(),
            })
            if len(results) >= 20:
                break
        if not results:
            print("[ProductHunt scrape] 0 items — page structure may have changed")
        return results
    except Exception as e:
        print(f"[ProductHunt scrape] {e}")
        return []


# ── Mastodon ─────────────────────────────────────────────────────────────────────
# No API key needed. Uses the public trending endpoint on mastodon.social.
# You can change the instance via MASTODON_INSTANCE in .env (default: mastodon.social).

def fetch_mastodon(limit: int = 20) -> List[Dict]:
    """Fetch trending posts from a Mastodon instance (no auth required)."""
    import os
    instance = os.getenv("MASTODON_INSTANCE", "mastodon.social").rstrip("/")
    results = []
    _headers = {**HEADERS,
                "User-Agent": "Mozilla/5.0 (compatible; Parallax/1.0)"}
    try:
        resp = requests.get(
            f"https://{instance}/api/v1/trends/statuses?limit={limit}",
            headers=_headers, timeout=10,
        )
        if resp.status_code != 200:
            print(f"[Mastodon] HTTP {resp.status_code}")
            return []
        for post in resp.json():
            content_html = post.get("content", "")
            content = BeautifulSoup(content_html, "html.parser").get_text(strip=True)
            if not content:
                continue
            account = post.get("account", {}).get("acct", "")
            url = post.get("url", "")
            favourites = post.get("favourites_count", 0)
            reblogs    = post.get("reblogs_count", 0)
            results.append({
                "source":      "mastodon",
                "title":       content[:120],
                "url":         url,
                "description": content[:300],
                "score":       favourites + reblogs,
                "by":          account,
                "ts":          datetime.now().isoformat(),
            })
    except Exception as e:
        print(f"[Mastodon] error: {e}")
    return results


# ── Dev.to ───────────────────────────────────────────────────────────────────────
# No API key needed for reading public articles.
# Optional: set DEVTO_API_KEY in .env for higher rate limits.
# Get a free key at: https://dev.to/settings/extensions (bottom of page → "DEV API Keys")

def fetch_devto(top_days: int = 3, limit: int = 30) -> List[Dict]:
    """Fetch top articles from Dev.to public API."""
    import os
    results = []
    _headers = {**HEADERS}
    api_key = os.getenv("DEVTO_API_KEY", "")
    if api_key:
        _headers["api-key"] = api_key
    try:
        resp = requests.get(
            f"https://dev.to/api/articles?top={top_days}&per_page={limit}",
            headers=_headers, timeout=10,
        )
        if resp.status_code != 200:
            print(f"[Dev.to] HTTP {resp.status_code}")
            return []
        for art in resp.json():
            title    = (art.get("title") or "").strip()
            url      = art.get("url") or art.get("canonical_url") or ""
            desc     = (art.get("description") or "").strip()[:300]
            tags     = ", ".join(art.get("tag_list") or [])
            reactions = art.get("public_reactions_count", 0)
            comments  = art.get("comments_count", 0)
            if not title:
                continue
            results.append({
                "source":      "devto",
                "title":       title,
                "url":         url,
                "description": f"{desc} [tags: {tags}]" if tags else desc,
                "score":       reactions + comments,
                "ts":          datetime.now().isoformat(),
            })
    except Exception as e:
        print(f"[Dev.to] error: {e}")
    return results


# ── NewsAPI ──────────────────────────────────────────────────────────────────────
# Free key at newsapi.org — 100 req/day on free tier.
# Set NEWSAPI_KEY in .env.
# Fetches top headlines across: technology, business, science, health, general.

def fetch_newsapi(limit_per_category: int = 10) -> List[Dict]:
    """Fetch top headlines from NewsAPI across multiple categories."""
    import os
    api_key = os.getenv("NEWSAPI_KEY", "")
    if not api_key:
        return []

    categories = ["technology", "business", "science", "general"]
    results = []
    seen_urls: set = set()

    for category in categories:
        try:
            resp = requests.get(
                "https://newsapi.org/v2/top-headlines",
                params={
                    "category": category,
                    "pageSize": limit_per_category,
                    "language": "en",
                    "apiKey":   api_key,
                },
                headers=HEADERS,
                timeout=10,
            )
            data = resp.json()
            if resp.status_code == 429 or data.get("code") == "rateLimited":
                print("[NewsAPI] daily limit reached — skipping")
                return results
            if resp.status_code != 200 or data.get("status") != "ok":
                print(f"[NewsAPI] HTTP {resp.status_code}: {data.get('message', 'unknown')}")
                continue
            for article in data.get("articles", []):
                title = (article.get("title") or "").strip()
                url   = (article.get("url") or "").strip()
                if not title or url in seen_urls or "[Removed]" in title:
                    continue
                seen_urls.add(url)
                desc    = (article.get("description") or "").strip()[:400]
                source  = (article.get("source") or {}).get("name", "")
                results.append({
                    "source":      "newsapi",
                    "category":    category,
                    "title":       title,
                    "url":         url,
                    "description": f"[{source}] {desc}" if source else desc,
                    "ts":          datetime.now().isoformat(),
                })
        except Exception as e:
            print(f"[NewsAPI] category={category} error: {e}")

    return results


# ── arXiv ─────────────────────────────────────────────────────────────────────────
# No API key needed. Uses the official arXiv Atom API.
# Fetches recent papers from AI/ML/NLP/Economics/Finance categories.

def fetch_arxiv(max_results: int = 30) -> List[Dict]:
    """Fetch recent papers from arXiv across AI, ML, NLP, economics, and finance."""
    import xml.etree.ElementTree as ET

    # Categories: cs.AI, cs.LG (ML), cs.CL (NLP/LLMs), econ.GN, q-fin.ST (quant finance)
    search_query = "cat:cs.AI OR cat:cs.LG OR cat:cs.CL OR cat:econ.GN OR cat:q-fin.ST"
    results = []

    try:
        resp = requests.get(
            "http://export.arxiv.org/api/query",
            params={
                "search_query": search_query,
                "sortBy":       "submittedDate",
                "sortOrder":    "descending",
                "max_results":  max_results,
            },
            headers=HEADERS,
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"[arXiv] HTTP {resp.status_code}")
            return []

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(resp.text)

        for entry in root.findall("atom:entry", ns):
            title   = (entry.findtext("atom:title", "", ns) or "").strip().replace("\n", " ")
            summary = (entry.findtext("atom:summary", "", ns) or "").strip().replace("\n", " ")[:400]
            url     = (entry.findtext("atom:id", "", ns) or "").strip()

            # Category tags
            cats = [c.get("term", "") for c in entry.findall("atom:category", ns)]
            cat_str = ", ".join(c for c in cats if c)

            if not title or not url:
                continue

            results.append({
                "source":      "arxiv",
                "title":       title,
                "url":         url,
                "description": f"[{cat_str}] {summary}" if cat_str else summary,
                "ts":          datetime.now().isoformat(),
            })
    except Exception as e:
        print(f"[arXiv] error: {e}")

    return results


# ── Google Trends ────────────────────────────────────────────────────────────────
# No API key needed — uses pytrends (unofficial Google Trends library).
# Install: pip install pytrends
# Set GOOGLE_TRENDS_GEO in .env (default: US). Examples: US, GB, DE, UA
# Note: Google may rate-limit if called too frequently. Interval >= 30 min recommended.

def fetch_google_trends(limit: int = 20) -> List[Dict]:
    """
    Fetch daily trending searches from Google Trends via pytrends.
    Hard 15s timeout — Google sometimes blocks/hangs automated requests.
    """
    import os
    import concurrent.futures
    try:
        from pytrends.request import TrendReq
    except ImportError:
        print("[Google Trends] pytrends not installed — run: pip install pytrends")
        return []

    geo = os.getenv("GOOGLE_TRENDS_GEO", "US")
    _pn_map = {
        "US": "united_states", "GB": "united_kingdom", "DE": "germany",
        "UA": "ukraine", "PL": "poland", "FR": "france", "CA": "canada",
        "AU": "australia", "IN": "india",
    }
    pn = _pn_map.get(geo.upper(), "united_states")

    def _fetch():
        pt = TrendReq(hl="en-US", tz=0, timeout=(8, 10))
        return pt.trending_searches(pn=pn)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_fetch)
            df = future.result(timeout=15)
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
                "score":       "",
                "ts":          datetime.now().isoformat(),
            })
        return results
    except concurrent.futures.TimeoutError:
        print("[Google Trends] timeout — Google may be rate-limiting, skipping")
        return []
    except Exception as e:
        print(f"[Google Trends] error: {e}")
        return []


# ── Dedup + Index ────────────────────────────────────────────────────────────────

def collect_and_index(index_to_rag: bool = True, on_progress=None) -> Dict:
    """
    Run all collectors, deduplicate, index new items into RAG.
    on_progress(step, current, total) — optional callback for live progress.
    Cross-process safe: uses a file lock so CLI and bot never run simultaneously,
    even in separate Docker containers sharing the same data/ volume.
    Returns summary dict.
    """
    try:
        from filelock import FileLock, Timeout
        _lock = FileLock(str(_RESEARCH_LOCK), timeout=600)  # wait up to 10 min
    except ImportError:
        # filelock not installed — fall back to no lock (single-process use)
        from contextlib import nullcontext
        _lock = nullcontext()

    with _lock:
        return _collect_and_index_inner(index_to_rag=index_to_rag, on_progress=on_progress)


def _collect_and_index_inner(index_to_rag: bool = True, on_progress=None) -> Dict:
    from core.rag_engine import splitter, vectorstore
    from langchain_core.documents import Document

    from core.rss import fetch_all_feeds as _fetch_rss, list_feeds as _list_rss_feeds
    _rss_sources = [("RSS Feeds", _fetch_rss)] if _list_rss_feeds() else []

    sources = [
        ("Hacker News",    lambda: fetch_hackernews(40)),
        ("Reddit",         fetch_reddit),
        ("GitHub",         lambda: fetch_github_trending("daily")),
        ("Product Hunt",   fetch_producthunt),
        ("Mastodon",       fetch_mastodon),
        ("Dev.to",         fetch_devto),
        ("Google Trends",  fetch_google_trends),
        ("NewsAPI",        fetch_newsapi),
        ("arXiv",          fetch_arxiv),
    ] + _rss_sources
    total_steps = len(sources)

    seen = _load_seen()
    all_items = []

    for i, (name, fn) in enumerate(sources, 1):
        if on_progress:
            on_progress(name, i, total_steps)
        else:
            print(f"[Intel] Fetching {name}...")
        all_items += fn()

    # Dedup
    new_items = []
    for item in all_items:
        h = _item_hash(item["title"], item.get("url", ""))
        if h not in seen:
            seen.add(h)
            new_items.append(item)

    _save_seen(seen)

    # Score new items with CCW (heuristics + LLM for 9-10)
    if new_items:
        try:
            from core.ccw import score_items
            score_items(new_items)
        except Exception as e:
            from core.error_logger import log_error
            log_error("intel.ccw", "CCW scoring failed", str(e))

    # Save raw feed
    existing = []
    if FEED_FILE.exists():
        try:
            existing = json.loads(FEED_FILE.read_text(encoding="utf-8"))[-2000:]
        except Exception:
            pass
    combined = existing + new_items
    FEED_FILE.write_text(json.dumps(combined[-3000:], ensure_ascii=False, indent=1), encoding="utf-8")

    # Index into RAG
    if on_progress:
        on_progress("Indexing into RAG", total_steps + 1, total_steps + 1)
    if index_to_rag and new_items:
        docs = []
        for item in new_items:
            source = item.get("source", "web")
            title  = item.get("title", "")
            url    = item.get("url", "")
            desc   = item.get("description") or item.get("selftext") or ""
            extra  = ""
            if source == "github_trending":
                extra = f"Language: {item.get('language','')}  Stars: {item.get('stars','')}  New today: {item.get('new_stars','')}"
            elif source in ("hackernews", "reddit"):
                extra = f"Score: {item.get('score',0)}  Comments: {item.get('comments',0)}"

            ccw = item.get("ccw", 0)
            ccw_str = f"CCW: {ccw}/10" + (f" — {item.get('ccw_reason','')}" if item.get("ccw_reason") else "")
            content = (
                f"[{source.upper()}] {title}\n"
                f"URL: {url}\n"
                f"{desc}\n{extra}\n"
                f"{ccw_str}\n"
                f"Collected: {item.get('ts','')}"
            )
            docs.append(Document(
                page_content=content,
                metadata={"source_file": f"intel:{source}", "url": url}
            ))
        chunks = splitter.split_documents(docs)
        vectorstore.add_documents(chunks)

    counts = {}
    for item in new_items:
        s = item.get("source", "unknown")
        counts[s] = counts.get(s, 0) + 1

    result = {
        "total_new":  len(new_items),
        "total_seen": len(all_items) - len(new_items),
        "by_source":  counts,
        "timestamp":  datetime.now().isoformat(),
        "new_items":  new_items,          # ← full list for summary generation
    }
    print(f"[Intel] Done: {len(new_items)} new items indexed.")
    return result


# ── Scheduler ────────────────────────────────────────────────────────────────────

_scheduler_started = False

def start_scheduler(interval_hours: int = 6, on_complete=None):
    """Start background scheduler that collects intel every N hours."""
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True

    def _loop():
        while True:
            try:
                result = collect_and_index()
                if on_complete:
                    on_complete(result)
            except Exception as e:
                print(f"[Scheduler] error: {e}")
            time.sleep(interval_hours * 3600)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    print(f"[Intel] Scheduler started — collecting every {interval_hours}h")


# ── Feed reader ──────────────────────────────────────────────────────────────────

def load_feed(source_filter: Optional[str] = None, limit: int = 100) -> List[Dict]:
    """Load cached feed from disk."""
    if not FEED_FILE.exists():
        return []
    try:
        items = json.loads(FEED_FILE.read_text(encoding="utf-8"))
        if source_filter:
            items = [i for i in items if i.get("source") == source_filter]
        return list(reversed(items))[:limit]
    except Exception:
        return []
