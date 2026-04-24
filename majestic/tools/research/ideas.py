"""Business ideas tool — generates startup/product ideas from recent trends."""
from majestic.tools.registry import tool


@tool(
    name="generate_ideas",
    description=(
        "Generate 5 business or product ideas based on recent tech and market trends. "
        "Use when the user asks for ideas, startup ideas, or business opportunities."
    ),
    input_schema={"type": "object", "properties": {}},
)
def generate_ideas() -> str:
    try:
        from core.agent import generate_ideas as _gen
        return _gen(force=True)
    except Exception as e:
        return f"Ideas generation error: {e}"
