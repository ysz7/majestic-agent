"""Market data tool — crypto, stocks, forex snapshot."""
from majestic.tools.registry import tool


@tool(
    name="get_market_data",
    description="Get current cryptocurrency, stock, and forex price snapshot.",
    input_schema={"type": "object", "properties": {}},
)
def get_market_data() -> str:
    try:
        from core.market_pulse import get_snapshot
        data = get_snapshot()
        if not data:
            return "Market data unavailable."
        lines = []
        for section, items in data.items():
            if isinstance(items, dict):
                lines.append(f"\n{section}:")
                for symbol, info in items.items():
                    if isinstance(info, dict):
                        price  = info.get("price") or info.get("usd", "?")
                        change = info.get("change_24h") or info.get("change_percent", "")
                        lines.append(
                            f"  {symbol}: {price}"
                            + (f" ({change:+.2f}%)" if isinstance(change, (int, float)) else "")
                        )
        return "\n".join(lines) if lines else str(data)
    except Exception as e:
        return f"Market data error: {e}"
