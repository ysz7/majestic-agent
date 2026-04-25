"""Market data tool — crypto, stocks, forex snapshot."""
from majestic.tools.registry import tool


@tool(
    name="get_market_data",
    description="Get current cryptocurrency, stock, and forex price snapshot.",
    input_schema={"type": "object", "properties": {}},
)
def get_market_data() -> str:
    try:
        from majestic.tools.research.market_data import collect_market_pulse, format_pulse
        data = collect_market_pulse()
        return format_pulse(data)
    except Exception as e:
        return f"Market data error: {e}"
