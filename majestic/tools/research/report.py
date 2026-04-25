"""Deep report tool — generates a structured report on any topic."""
from majestic.tools.registry import tool


@tool(
    name="get_report",
    description=(
        "Generate a detailed structured report on any topic. "
        "Searches local knowledge base first, falls back to web search. "
        "Saves the report to exports/. "
        "Use when the user asks for a report, analysis, or deep dive on a specific topic."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "The topic to generate a report about",
            },
        },
        "required": ["topic"],
    },
)
def get_report(topic: str) -> str:
    from majestic.rag import ask
    from majestic.config import get

    scope    = get("search_mode", "all")
    question = (
        f"Create a detailed structured report on: «{topic}». "
        "Include all relevant data. Divide into sections with headings."
    )
    result = ask(question, scope=scope)
    answer = result.get("answer", "")

    _no_data = not answer.strip() or any(
        p in answer.lower() for p in ("no relevant", "i don't have", "not found")
    )
    if _no_data or not result.get("sources"):
        try:
            from majestic.tools.web.websearch import search
            from majestic.llm import get_provider
            lang = get("language", "EN")
            web = search(topic, max_results=6)
            if web:
                ctx = "\n\n---\n\n".join(
                    f"[{r['title']}]\n{r['content']}\nSource: {r['url']}" for r in web
                )
                prompt = (
                    f"Create a detailed structured report on: «{topic}».\n"
                    f"Use ONLY the web results below. Respond in {lang}.\n\n{ctx[:6000]}\n\nReport:"
                )
                resp = get_provider().complete([{"role": "user", "content": prompt}])
                answer = resp.content
        except Exception as e:
            answer = answer or f"Could not generate report: {e}"

    # Save to exports
    try:
        from datetime import datetime
        from majestic.constants import EXPORTS_DIR
        export_dir = EXPORTS_DIR
        export_dir.mkdir(parents=True, exist_ok=True)
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = topic[:40].replace(" ", "_").replace("/", "-")
        out  = export_dir / f"report_{slug}_{ts}.md"
        out.write_text(
            f"# Report: {topic}\n_Created: {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n\n{answer}",
            encoding="utf-8",
        )
    except Exception:
        pass

    return answer
