"""
Market price fetcher — CoinGecko (crypto) + Yahoo Finance (indices/commodities/forex).
Both sources are free and require no API keys.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Majestic-Research/1.0)"}

# Major indices, commodities, forex tracked via Yahoo Finance
_YAHOO_SYMBOLS: list[tuple[str, str, str]] = [
    ("^SPX",     "S&P 500",    "index"),
    ("^IXIC",    "Nasdaq",     "index"),
    ("^DJI",     "Dow Jones",  "index"),
    ("^VIX",     "VIX",        "index"),
    ("GC=F",     "Gold",       "commodity"),
    ("CL=F",     "Oil WTI",    "commodity"),
    ("DX-Y.NYB", "DXY",        "forex"),
]


async def _fetch_coingecko(client: httpx.AsyncClient) -> list[dict]:
    """Top 20 crypto by market cap — price, 24h%, 7d%."""
    try:
        r = await client.get(
            "https://api.coingecko.com/api/v3/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 20,
                "page": 1,
                "price_change_percentage": "24h,7d",
            },
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as exc:
        logger.debug("CoinGecko fetch failed: %s", exc)
        return []

    results: list[dict] = []
    for coin in data:
        results.append({
            "symbol":     coin.get("symbol", "").upper(),
            "name":       coin.get("name", ""),
            "asset_class": "crypto",
            "price":      coin.get("current_price"),
            "change_24h": coin.get("price_change_percentage_24h"),
            "change_7d":  coin.get("price_change_percentage_7d_in_currency"),
            "market_cap": coin.get("market_cap"),
            "volume_24h": coin.get("total_volume"),
            "currency":   "USD",
        })
    return results


async def _fetch_yahoo_symbol(
    client: httpx.AsyncClient,
    symbol: str,
    name: str,
    asset_class: str,
) -> dict | None:
    """Single Yahoo Finance chart call → price + 24h change."""
    try:
        r = await client.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={"interval": "1d", "range": "5d"},
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        meta = r.json()["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice") or meta.get("previousClose")
        prev  = meta.get("previousClose") or meta.get("chartPreviousClose")
        change_24h = round((price - prev) / prev * 100, 2) if (price and prev) else None
        return {
            "symbol":     symbol,
            "name":       name,
            "asset_class": asset_class,
            "price":      price,
            "change_24h": change_24h,
            "change_7d":  None,
            "market_cap": None,
            "volume_24h": meta.get("regularMarketVolume"),
            "currency":   meta.get("currency", "USD"),
        }
    except Exception as exc:
        logger.debug("Yahoo Finance %s failed: %s", symbol, exc)
        return None


async def fetch_prices() -> list[dict]:
    """Fetch crypto (CoinGecko) + major indices/commodities/forex (Yahoo Finance).

    Returns list of price dicts. Empty list on total failure.
    """
    async with httpx.AsyncClient() as client:
        crypto_task = _fetch_coingecko(client)
        yahoo_tasks = [
            _fetch_yahoo_symbol(client, sym, name, cls)
            for sym, name, cls in _YAHOO_SYMBOLS
        ]
        crypto, *yahoo_results = await asyncio.gather(
            crypto_task, *yahoo_tasks, return_exceptions=True
        )

    results: list[dict] = []
    if isinstance(crypto, list):
        results.extend(crypto)

    for item in yahoo_results:
        if isinstance(item, dict) and item is not None:
            results.append(item)

    return results


def format_prices_for_corpus(prices: list[dict], fetched_at: str = "") -> str:
    """Render price list as a compact corpus block for LLM consumption."""
    if not prices:
        return ""

    ts_note = f" (fetched {fetched_at[:16]})" if fetched_at else ""
    lines = [f"=== LIVE MARKET DATA{ts_note} ===\n"]

    crypto = [p for p in prices if p.get("asset_class") == "crypto"]
    other  = [p for p in prices if p.get("asset_class") != "crypto"]

    if crypto:
        lines.append("[CRYPTO — top by market cap]")
        for p in crypto[:10]:
            price_str  = f"${p['price']:,.2f}" if p.get("price") else "n/a"
            ch24       = p.get("change_24h")
            ch7        = p.get("change_7d")
            ch24_str   = f"{ch24:+.1f}% (24h)" if ch24 is not None else ""
            ch7_str    = f"{ch7:+.1f}% (7d)" if ch7 is not None else ""
            mcap       = p.get("market_cap")
            mcap_str   = f" | mcap ${mcap/1e9:.1f}B" if mcap else ""
            parts = filter(None, [ch24_str, ch7_str])
            lines.append(f"{p['symbol']}: {price_str} {' | '.join(parts)}{mcap_str}")
        lines.append("")

    if other:
        lines.append("[INDICES & MACRO]")
        for p in other:
            price_str = f"{p['price']:,.2f}" if p.get("price") else "n/a"
            if p.get("currency") == "USD" and p.get("asset_class") == "commodity":
                price_str = f"${price_str}"
            ch24 = p.get("change_24h")
            ch24_str = f"{ch24:+.1f}% (24h)" if ch24 is not None else ""
            lines.append(f"{p['name']}: {price_str} {ch24_str}".strip())
        lines.append("")

    return "\n".join(lines)


def format_prices_for_display(prices: list[dict]) -> str:
    """Compact one-line-per-asset display for terminal output (plain text fallback)."""
    if not prices:
        return ""

    lines: list[str] = []
    crypto = [p for p in prices if p.get("asset_class") == "crypto"]
    other  = [p for p in prices if p.get("asset_class") != "crypto"]

    def _pct(ch: float | None) -> str:
        if ch is None:
            return "   n/a"
        sign = "+" if ch >= 0 else ""
        return f"{sign}{ch:.1f}%"

    if crypto:
        lines.append("Crypto")
        for p in crypto[:10]:
            price_str = f"${p['price']:>12,.2f}" if p.get("price") else "           n/a"
            ch24 = _pct(p.get("change_24h"))
            ch7  = _pct(p.get("change_7d"))
            lines.append(f"  {p['symbol']:<6} {price_str}  {ch24:<9}  {ch7} (7d)")

    if other:
        if crypto:
            lines.append("")
        lines.append("Indices & Macro")
        for p in other:
            price = p.get("price", 0)
            if p.get("asset_class") == "commodity":
                price_str = f"${price:>12,.2f}"
            else:
                price_str = f" {price:>12,.2f}"
            ch24 = _pct(p.get("change_24h"))
            lines.append(f"  {p['name']:<13} {price_str}  {ch24}")

    return "\n".join(lines)


def render_prices_table(prices: list[dict], fetched_at: str = ""):
    """Return a Rich Table for market snapshot display. Returns None if Rich unavailable."""
    try:
        from rich.table import Table
        from rich.text import Text
    except ImportError:
        return None

    if not prices:
        return None

    def _pct_text(ch: float | None, suffix: str = "") -> Text:
        if ch is None:
            return Text("-", style="dim")
        sign = "+" if ch >= 0 else ""
        style = "green" if ch >= 0 else "red"
        return Text(f"{sign}{ch:.1f}%{suffix}", style=style)

    def _price_str(p: dict) -> str:
        price = p.get("price")
        if price is None:
            return "n/a"
        if p.get("asset_class") in ("crypto", "commodity"):
            return f"${price:,.2f}"
        return f"{price:,.2f}"

    def _mcap_str(p: dict) -> str:
        mc = p.get("market_cap")
        if not mc:
            return ""
        if mc >= 1e12:
            return f"${mc/1e12:.2f}T"
        return f"${mc/1e9:.0f}B"

    ts_note = f"  [dim]{fetched_at[:16]}[/dim]" if fetched_at else ""
    crypto = [p for p in prices if p.get("asset_class") == "crypto"]
    other  = [p for p in prices if p.get("asset_class") != "crypto"]

    table = Table(
        title=f"[bold]Market Snapshot[/bold]{ts_note}",
        title_justify="left",
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        pad_edge=False,
        expand=False,
    )
    table.add_column("Asset",   style="bold", min_width=10)
    table.add_column("Price",   justify="right", min_width=12)
    table.add_column("24h %",   justify="right", min_width=8)
    table.add_column("7d %",    justify="right", min_width=8)
    table.add_column("Mcap",    justify="right", min_width=8, style="dim")

    if crypto:
        table.add_row(Text("Crypto", style="cyan bold"), "", "", "", "", end_section=False)
        for p in crypto[:10]:
            table.add_row(
                p.get("name", p.get("symbol", "")),
                _price_str(p),
                _pct_text(p.get("change_24h")),
                _pct_text(p.get("change_7d")),
                _mcap_str(p),
            )

    if other:
        table.add_row(Text("Indices & Macro", style="cyan bold"), "", "", "", "", end_section=False)
        for p in other:
            table.add_row(
                p.get("name", p.get("symbol", "")),
                _price_str(p),
                _pct_text(p.get("change_24h")),
                Text("-", style="dim"),
                "",
            )

    return table
