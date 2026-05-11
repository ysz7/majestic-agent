"""
monitor_topics.py — Check and update monitored topics.

Usage:
    python monitor_topics.py                              # check all active topics
    python monitor_topics.py --topic "nuclear energy"    # check specific topic
    python monitor_topics.py add "nuclear energy" --query "nuclear SMR investment 2026"
"""

import json
import sys
import subprocess
import argparse
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

_PROFILE_ROOT = Path(__file__).parents[2]  # = profiles/world_intel/
_PROJECT_ROOT = Path(__file__).parents[4]  # = c:/ysz/DEV/majestic-agent/
_DATA_DIR = _PROFILE_ROOT / "data"
_OUTPUT_DIR = _PROFILE_ROOT / "workspace" / "output"
_TOOLS_DIR = Path(__file__).parent

# ---------------------------------------------------------------------------
# Env / LLM helpers
# ---------------------------------------------------------------------------

def _load_env() -> dict:
    env = {}
    for path in [_PROJECT_ROOT / ".env", _PROFILE_ROOT / ".env"]:
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    return env


def _call_llm(prompt: str, system: str, env: dict, max_tokens: int = 2000) -> str:
    import httpx
    api_key = env.get("OPENROUTER_API_KEY") or env.get("ANTHROPIC_API_KEY") or env.get("OPENAI_API_KEY")
    ollama_url = env.get("OLLAMA_BASE_URL")
    if not api_key and not ollama_url:
        return "[LLM unavailable]"
    if ollama_url and not api_key:
        url = f"{ollama_url.rstrip('/')}/v1/chat/completions"
        model = env.get("OLLAMA_MODEL", "llama3.2")
        headers = {"Content-Type": "application/json"}
    else:
        url = "https://openrouter.ai/api/v1/chat/completions"
        model = env.get("MAJESTIC_MODEL_REASON", "anthropic/claude-sonnet-4-5")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/majestic-agent",
            "X-Title": "Majestic World Intel Agent",
        }
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    try:
        resp = httpx.post(url, headers=headers, json=body, timeout=120)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        return f"[LLM error: {exc}]"


# ---------------------------------------------------------------------------
# Subprocess helper
# ---------------------------------------------------------------------------

def _run_tool(tool_name: str, *args) -> dict | list:
    result = subprocess.run(
        [sys.executable, str(_TOOLS_DIR / tool_name), *args],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode == 0 and result.stdout.strip():
        try:
            return json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            return {}
    return {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _topic_slug(name: str) -> str:
    """Convert topic name to a safe filename slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")
    return slug or "topic"


def _now_str() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_recent_24h(extracted_at: str) -> bool:
    """Return True if extracted_at is within the last 24 hours."""
    try:
        ts = datetime.fromisoformat(extracted_at.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - ts) <= timedelta(hours=24)
    except (ValueError, TypeError):
        return False


def _keywords_from_topic(topic: dict) -> list[str]:
    """Extract search keywords from a topic record."""
    name = topic.get("name", "")
    query = topic.get("query", "")
    # Split both name and query into keywords
    words = set()
    for text in [name, query]:
        for word in re.split(r"[\s,;|]+", text.lower()):
            word = word.strip()
            if len(word) >= 3:
                words.add(word)
    return list(words)


# ---------------------------------------------------------------------------
# Core: check a single topic
# ---------------------------------------------------------------------------

def _check_topic(topic: dict, env: dict) -> dict:
    """
    Check news and signals for a single topic.
    Returns: {"topic": name, "alert": bool, "alert_reason": str, "report_path": str}
    """
    topic_name = topic.get("name", "")
    topic_query = topic.get("query", "") or topic_name
    slug = _topic_slug(topic_name)
    keywords = _keywords_from_topic(topic)

    # a. Search news.db by topic name
    news_by_name = _run_tool("db_news.py", "search", topic_name)
    if not isinstance(news_by_name, list):
        news_by_name = []

    # b. Also search with the stored query if different from name
    news_by_query: list[dict] = []
    if topic_query and topic_query.lower() != topic_name.lower():
        news_by_query = _run_tool("db_news.py", "search", topic_query)
        if not isinstance(news_by_query, list):
            news_by_query = []

    # Deduplicate news by id
    seen_ids: set[str] = set()
    related_news: list[dict] = []
    for item in news_by_name + news_by_query:
        item_id = item.get("id", "")
        if item_id not in seen_ids:
            seen_ids.add(item_id)
            related_news.append(item)

    # c. Load related signals by scanning signals where data_json contains topic keywords
    related_signals: list[dict] = []
    seen_sig_ids: set[str] = set()

    for kw in keywords[:5]:  # limit keyword searches to avoid too many subprocess calls
        # Search funding signals
        for sig_type in ("funding_round", "policy_change", "market_move"):
            sigs = _run_tool("db_signals.py", "get_by_type", sig_type, "--limit", "100")
            if not isinstance(sigs, list):
                continue
            for sig in sigs:
                sig_id = sig.get("id", "")
                if sig_id in seen_sig_ids:
                    continue
                try:
                    data_text = sig.get("data_json", "{}").lower()
                except AttributeError:
                    data_text = ""
                if kw in data_text:
                    seen_sig_ids.add(sig_id)
                    related_signals.append(sig)

    # Sort signals by extracted_at descending
    related_signals.sort(key=lambda x: x.get("extracted_at", ""), reverse=True)

    # d. Detect alert: significance="landmark" or "high" AND extracted in last 24h
    alert = False
    alert_reason = ""
    for sig in related_signals:
        sig_significance = (sig.get("significance") or "").lower()
        extracted_at = sig.get("extracted_at", "")
        if sig_significance in ("landmark", "high") and _is_recent_24h(extracted_at):
            alert = True
            try:
                data = json.loads(sig.get("data_json", "{}"))
            except (json.JSONDecodeError, AttributeError):
                data = {}
            desc = data.get("description") or data.get("title") or data.get("company") or str(data)[:80]
            alert_reason = f"[{sig_significance.upper()}] {desc} (at {extracted_at})"
            break

    # e. Build LLM summary
    news_summary = "\n".join(
        f"- [{item.get('date', '')}] {item.get('headline', '')} (source: {item.get('source', '')})"
        for item in related_news[:15]
    ) or "_No related news found._"

    signals_summary = "\n".join(
        f"- [{sig.get('type', '')}] {sig.get('data_json', '')[:120]} (significance: {sig.get('significance', '')})"
        for sig in related_signals[:10]
    ) or "_No related signals found._"

    llm_summary = _call_llm(
        prompt=(
            f"Topic: {topic_name}\n"
            f"Search query: {topic_query}\n\n"
            f"Related news articles:\n{news_summary}\n\n"
            f"Related signals:\n{signals_summary}"
        ),
        system=(
            f"Given these news articles and signals related to '{topic_name}', write a monitoring update. "
            "What happened this week? Key signals? Trend direction? "
            "Alert if significance is high/landmark."
        ),
        env=env,
        max_tokens=600,
    )

    # f. Format signals list for report
    signal_lines = []
    for sig in related_signals[:20]:
        try:
            data = json.loads(sig.get("data_json", "{}"))
        except (json.JSONDecodeError, AttributeError):
            data = {}
        desc = data.get("description") or data.get("title") or data.get("company") or str(data)[:100]
        sig_type = sig.get("type", "")
        significance = sig.get("significance", "")
        extracted_at = sig.get("extracted_at", "")[:10]
        signal_lines.append(f"- [{extracted_at}] [{sig_type}] {desc} (significance: {significance})")
    signals_section = "\n".join(signal_lines) if signal_lines else "_No signals found._"

    # Format news list for report
    news_lines = []
    for item in related_news[:20]:
        headline = item.get("headline", "")
        source = item.get("source", "")
        url = item.get("source_url", "")
        date = item.get("date", "")
        news_lines.append(f"- [{date}] {headline} — [{source}]({url})")
    news_section = "\n".join(news_lines) if news_lines else "_No related articles found._"

    # Alert block
    if alert:
        alert_block = f"**ALERT: High significance signal detected:** {alert_reason}"
    else:
        alert_block = "No alerts."

    # g. Write topic report
    now_display = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    report_md = f"""# Topic Monitor: {topic_name}
Last updated: {now_display}

## Recent Activity
{llm_summary}

## Signals Found
{signals_section}

## Related News
{news_section}

## Alert
{alert_block}
"""

    report_dir = _OUTPUT_DIR / "reports" / "topics"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{slug}.md"
    report_path.write_text(report_md, encoding="utf-8")

    # h. Mark topic as checked
    _run_tool("db_topics.py", "mark_checked", topic_name)

    return {
        "topic": topic_name,
        "alert": alert,
        "alert_reason": alert_reason,
        "report_path": str(report_path),
        "news_count": len(related_news),
        "signal_count": len(related_signals),
    }


# ---------------------------------------------------------------------------
# Public commands
# ---------------------------------------------------------------------------

def cmd_add(name: str, query: str) -> dict:
    """Add a new monitored topic."""
    result = _run_tool("db_topics.py", "add", name, "--query", query)
    if not isinstance(result, dict):
        result = {}
    result["name"] = name
    result["query"] = query
    return result


def cmd_check(topic_name: str = "") -> dict:
    """Check one or all active topics."""
    env = _load_env()

    if topic_name:
        topic = _run_tool("db_topics.py", "get_by_name", topic_name)
        if not isinstance(topic, dict) or not topic:
            return {"error": f"Topic not found: {topic_name}", "topics_checked": 0, "alerts": [], "updated_reports": []}
        topics = [topic]
    else:
        topics = _run_tool("db_topics.py", "get_all_active")
        if not isinstance(topics, list):
            topics = []

    alerts = []
    updated_reports = []
    topics_checked = 0

    for topic in topics:
        check_result = _check_topic(topic, env)
        topics_checked += 1
        updated_reports.append(check_result["report_path"])
        if check_result["alert"]:
            alerts.append({
                "topic": check_result["topic"],
                "reason": check_result["alert_reason"],
            })

    return {
        "topics_checked": topics_checked,
        "alerts": alerts,
        "updated_reports": updated_reports,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check and update monitored topics.")
    sub = parser.add_subparsers(dest="command")

    # add
    p_add = sub.add_parser("add", help="Add a new monitored topic.")
    p_add.add_argument("name", help="Topic name.")
    p_add.add_argument("--query", default="", help="Search query for this topic.")

    # check (default)
    parser.add_argument("--topic", default="", help="Check a specific topic by name.")

    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    command = getattr(args, "command", None)

    if command == "add":
        result = cmd_add(args.name, args.query)
    else:
        # Default: check topics
        topic_name = getattr(args, "topic", "")
        result = cmd_check(topic_name)

    print(json.dumps(result, indent=2))
