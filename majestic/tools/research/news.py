"""News tools — collect signals and retrieve top news by CCW score."""
from majestic.tools.registry import tool


@tool(
    name="run_research",
    description=(
        "Collect fresh signals from all sources (HN, Reddit, GitHub, Arxiv, RSS, etc.) "
        "and index them. Returns a summary of what was found. "
        "Use when the user asks to research, gather intel, or update news feed."
    ),
    input_schema={"type": "object", "properties": {}},
)
def run_research() -> str:
    from majestic.tools.research.collect import collect_and_index
    try:
        result = collect_and_index()
    except Exception as e:
        return f"Research error: {e}"

    total_new = result.get("total_new", 0)
    by_src    = result.get("by_source", {})
    lines     = [f"Research complete. {total_new} new items collected."]
    for src, count in by_src.items():
        if count:
            lines.append(f"  {src}: {count} new")

    new_items = result.get("new_items", [])
    if new_items:
        try:
            from majestic.tools.research.briefing import quick_summary_from_new
            summary = quick_summary_from_new(new_items)
            lines.append("\n" + summary)
        except Exception:
            pass

    return "\n".join(lines)


@tool(
    name="get_news",
    description=(
        "Return recent top news items sorted by CCW (cross-source confidence) score. "
        "Use when the user wants to see the latest news or trending topics."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Number of news items to return (default 10)",
            },
        },
    },
)
def get_news(limit: int = 10) -> str:
    from majestic.tools.research.collect import load_feed
    items = load_feed(limit=limit * 3)
    if not items:
        return "No news yet. Run research first."

    items = sorted(
        items,
        key=lambda x: (x.get("ccw", 0), x.get("score") or x.get("stars") or 0),
        reverse=True,
    )[:limit]

    lines = []
    for i, item in enumerate(items, 1):
        src   = item.get("source", "")
        title = item.get("title", "")
        url   = item.get("url", "")
        ccw   = item.get("ccw", 0)
        ccw_s = f" [CCW:{ccw}]" if ccw else ""
        lines.append(f"{i}. [{src}] {title}{ccw_s}")
        if url:
            lines.append(f"   {url}")
    return "\n".join(lines)
