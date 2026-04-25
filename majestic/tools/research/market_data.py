"""Market data — CoinGecko, forex, Alpha Vantage, Finnhub. SQLite history."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional

import requests

from majestic.constants import MAJESTIC_HOME

_DB_PATH = MAJESTIC_HOME / "market_history.db"
HEADERS  = {"User-Agent": "Majestic-Agent/1.0"}


def _get_conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            ts      TEXT NOT NULL,
            crypto  TEXT NOT NULL,
            stocks  TEXT NOT NULL,
            forex   TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def _save_snapshot(data: Dict) -> None:
    conn = _get_conn()
    conn.execute(
        "INSERT INTO snapshots (ts, crypto, stocks, forex) VALUES (?, ?, ?, ?)",
        (data["ts"], json.dumps(data.get("crypto", [])), json.dumps(data.get("stocks", [])), json.dumps(data.get("forex", []))),
    )
    conn.commit()
    conn.close()


def load_latest_pulse() -> Optional[Dict]:
    try:
        conn = _get_conn()
        row  = conn.execute("SELECT ts, crypto, stocks, forex FROM snapshots ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        if not row:
            return None
        return {"ts": row[0], "crypto": json.loads(row[1]), "stocks": json.loads(row[2]), "forex": json.loads(row[3])}
    except Exception:
        return None


def load_history(limit: int = 10) -> List[Dict]:
    try:
        conn = _get_conn()
        rows = conn.execute("SELECT id, ts, crypto, stocks, forex FROM snapshots ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return [{"id": r[0], "ts": r[1], "crypto": json.loads(r[2]), "stocks": json.loads(r[3]), "forex": json.loads(r[4])} for r in rows]
    except Exception:
        return []


def fetch_crypto(coins: str = "bitcoin,ethereum,solana") -> List[Dict]:
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": coins, "vs_currencies": "usd", "include_24hr_change": "true",
                    "include_market_cap": "true", "include_24hr_vol": "true"},
            headers=HEADERS, timeout=10,
        )
        return [
            {"type": "crypto", "symbol": coin, "price": info.get("usd", 0),
             "change": round(info.get("usd_24h_change") or 0, 2),
             "mcap": info.get("usd_market_cap", 0), "vol24h": info.get("usd_24h_vol", 0)}
            for coin, info in resp.json().items()
        ]
    except Exception as e:
        print(f"[Market] CoinGecko error: {e}")
        return []


def fetch_forex(base: str = "USD", targets: str = "EUR,GBP,JPY") -> List[Dict]:
    try:
        rates = requests.get(f"https://open.er-api.com/v6/latest/{base}", headers=HEADERS, timeout=10).json().get("rates", {})
        return [{"type": "forex", "pair": f"{base}/{c.strip()}", "rate": rates[c.strip()]} for c in targets.split(",") if c.strip() in rates]
    except Exception as e:
        print(f"[Market] Forex error: {e}")
        return []


def fetch_stocks_av(symbols: str, api_key: str) -> List[Dict]:
    if not api_key:
        return []
    results = []
    for symbol in [s.strip() for s in symbols.split(",")][:5]:
        try:
            quote = requests.get("https://www.alphavantage.co/query",
                params={"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": api_key},
                headers=HEADERS, timeout=10).json().get("Global Quote", {})
            if not quote:
                continue
            results.append({
                "type": "stock", "symbol": symbol,
                "price": float(quote.get("05. price", 0)),
                "change": round(float(quote.get("10. change percent", "0%").replace("%", "")), 2),
                "volume": quote.get("06. volume", ""),
            })
        except Exception as e:
            print(f"[Market] AV {symbol} error: {e}")
    return results


def fetch_stocks_finnhub(symbols: str, api_key: str) -> List[Dict]:
    if not api_key:
        return []
    results = []
    for symbol in [s.strip() for s in symbols.split(",")][:10]:
        try:
            q = requests.get("https://finnhub.io/api/v1/quote",
                params={"symbol": symbol, "token": api_key}, headers=HEADERS, timeout=8).json()
            if not q.get("c"):
                continue
            price = q.get("c", 0)
            prev  = q.get("pc", price)
            results.append({
                "type": "stock", "symbol": symbol, "price": price,
                "change": round(((price - prev) / prev * 100) if prev else 0, 2),
                "high": q.get("h"), "low": q.get("l"),
            })
        except Exception as e:
            print(f"[Market] Finnhub {symbol} error: {e}")
    return results


def collect_market_pulse() -> Dict:
    coins   = os.getenv("CRYPTO_COINS", "bitcoin,ethereum,solana")
    symbols = os.getenv("STOCK_SYMBOLS", "AAPL,NVDA,MSFT")
    forex_t = os.getenv("FOREX_PAIRS", "EUR,GBP,JPY").replace("/", ",").replace("USD", "").strip(",") or "EUR,GBP,JPY"
    av_key  = os.getenv("ALPHAVANTAGE_KEY", "")
    fh_key  = os.getenv("FINNHUB_KEY", "")

    data = {"ts": datetime.now().isoformat(), "crypto": fetch_crypto(coins), "forex": fetch_forex("USD", forex_t), "stocks": []}
    if fh_key:
        data["stocks"] = fetch_stocks_finnhub(symbols, fh_key)
    elif av_key:
        data["stocks"] = fetch_stocks_av(symbols, av_key)
    _save_snapshot(data)
    return data


def _arrow(change: float) -> str:
    if change > 2:  return "🟢 ▲"
    if change > 0:  return "🟩 ↑"
    if change < -2: return "🔴 ▼"
    if change < 0:  return "🟥 ↓"
    return "⬜ —"


def format_pulse(data: Dict) -> str:
    if not data:
        return "No data. Run /market first."
    ts = data.get("ts", "")
    try:
        ts = datetime.fromisoformat(ts).strftime("%d.%m.%Y %H:%M")
    except Exception:
        pass
    lines = [f"Updated: {ts}\n"]
    if data.get("crypto"):
        lines.append("🪙 Crypto")
        for c in data["crypto"]:
            lines.append(f"  {_arrow(c.get('change', 0))} {c['symbol'].capitalize():<12} ${c['price']:>12,.2f}  {c.get('change', 0):+.2f}%")
    if data.get("stocks"):
        lines.append("\n📈 Stocks")
        for s in data["stocks"]:
            lines.append(f"  {_arrow(s.get('change', 0))} {s['symbol']:<12} ${s['price']:>10,.2f}  {s.get('change', 0):+.2f}%")
    if data.get("forex"):
        lines.append("\n💱 Forex (USD →)")
        for f in data["forex"]:
            lines.append(f"  {f['pair']:<12} {f['rate']:.4f}")
    return "\n".join(lines)


def market_context_for_llm(snapshots: int = 3) -> str:
    history = load_history(limit=snapshots)
    if not history:
        return ""
    lines = []
    for snap in reversed(history):
        ts = snap["ts"]
        try:
            ts = datetime.fromisoformat(ts).strftime("%d.%m %H:%M")
        except Exception:
            pass
        lines.append(f"[{ts}]")
        for c in snap.get("crypto", []):
            lines.append(f"  {c['symbol']}: ${c['price']:,.0f} ({c.get('change', 0):+.1f}%)")
        for s in snap.get("stocks", []):
            lines.append(f"  {s['symbol']}: ${s['price']:,.2f} ({s.get('change', 0):+.1f}%)")
        for f in snap.get("forex", []):
            lines.append(f"  {f['pair']}: {f['rate']:.4f}")
    return "\n".join(lines)
