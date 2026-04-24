"""Briefing tool — full market/tech briefing with predictions and capital flows."""
from majestic.tools.registry import tool


@tool(
    name="get_briefing",
    description=(
        "Generate a full analytical briefing covering recent tech/market signals, "
        "predictions, and capital flow analysis. "
        "Use when the user asks for a briefing, predictions, forecasts, or capital flows."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "How many days of data to include (default 14)",
            },
            "focus": {
                "type": "string",
                "enum": ["full", "predictions", "flows"],
                "description": (
                    "full = complete briefing; "
                    "predictions = forecasts only; "
                    "flows = capital flows only"
                ),
            },
        },
    },
)
def get_briefing(days: int = 14, focus: str = "full") -> str:
    from core.trends import generate_briefing, generate_predictions, generate_money_flows
    try:
        if focus == "predictions":
            return generate_predictions(days=days)
        if focus == "flows":
            return generate_money_flows(days=days)
        return generate_briefing(days=days)
    except Exception as e:
        return f"Briefing error: {e}"
