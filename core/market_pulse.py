"""
Market Pulse — market data via free APIs
- CoinGecko     : crypto (no key)
- open.er-api   : forex (no key)
- Alpha Vantage : stocks + macro (free key)
- Finnhub       : stocks real-time (free key)

Storage: SQLite — each /market call appends a new snapshot row.
"""

import os
import sqlite3
import json
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv
load_dotenv()

DB_PATH = Path(__file__).parent.parent / "data" / "intel" / "market_history.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "CLOUDeVAULT/1.0"}


# ── SQLite setup ─────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
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


def _save_snapshot(data: Dict):
    conn = _get_conn()
    conn.execute(
        "INSERT INTO snapshots (ts, crypto, stocks, forex) VALUES (?, ?, ?, ?)",
        (
            data["ts"],
            json.dumps(data.get("crypto", []), ensure_ascii=False),
            json.dumps(data.get("stocks", []), ensure_ascii=False),
            json.dumps(data.get("forex",  []), ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()


def load_latest_pulse() -> Optional[Dict]:
    """Return the most recent snapshot from DB."""
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT ts, crypto, stocks, forex FROM snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if not row:
            return None
        return {
            "ts":     row[0],
            "crypto": json.loads(row[1]),
            "stocks": json.loads(row[2]),
            "forex":  json.loads(row[3]),
        }
    except Exception:
        return None


def load_history(limit: int = 10) -> List[Dict]:
    """Return last N snapshots from DB (newest first)."""
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT id, ts, crypto, stocks, forex FROM snapshots ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        result = []
        for row in rows:
            result.append({
                "id":     row[0],
                "ts":     row[1],
                "crypto": json.loads(row[2]),
                "stocks": json.loads(row[3]),
                "forex":  json.loads(row[4]),
            })
        return result
    except Exception:
        return []


# ── Config ───────────────────────────────────────────────────────────────────

def get_market_config() -> dict:
    return {
        "alphavantage_key": os.getenv("ALPHAVANTAGE_KEY", ""),
        "finnhub_key":      os.getenv("FINNHUB_KEY", ""),
        "crypto_coins":     os.getenv("CRYPTO_COINS", "bitcoin,ethereum,solana"),
        "stock_symbols":    os.getenv("STOCK_SYMBOLS", "AAPL,NVDA,MSFT"),
        "forex_pairs":      os.getenv("FOREX_PAIRS", "EUR,GBP,JPY"),
    }


# ── CoinGecko ────────────────────────────────────────────────────────────────

def fetch_crypto(coins: str = "bitcoin,ethereum,solana") -> List[Dict]:
    results = []
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={
                "ids": coins,
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_market_cap": "true",
                "include_24hr_vol": "true",
            },
            headers=HEADERS, timeout=10,
        )
        data = resp.json()
        for coin, info in data.items():
            change = info.get("usd_24h_change", 0) or 0
            results.append({
                "type":   "crypto",
                "symbol": coin,
                "price":  info.get("usd", 0),
                "change": round(change, 2),
                "mcap":   info.get("usd_market_cap", 0),
                "vol24h": info.get("usd_24h_vol", 0),
            })
    except Exception as e:
        print(f"[Market] CoinGecko error: {e}")
    return results


# ── Forex ────────────────────────────────────────────────────────────────────

def fetch_forex(base: str = "USD", targets: str = "EUR,GBP,JPY") -> List[Dict]:
    results = []
    try:
        resp = requests.get(
            f"https://open.er-api.com/v6/latest/{base}",
            headers=HEADERS, timeout=10,
        )
        rates = resp.json().get("rates", {})
        for currency in [t.strip() for t in targets.split(",")]:
            if currency in rates:
                results.append({
                    "type": "forex",
                    "pair": f"{base}/{currency}",
                    "rate": rates[currency],
                })
    except Exception as e:
        print(f"[Market] Forex error: {e}")
    return results


# ── Alpha Vantage ─────────────────────────────────────────────────────────────

def fetch_stocks_av(symbols: str, api_key: str) -> List[Dict]:
    if not api_key:
        return []
    results = []
    for symbol in [s.strip() for s in symbols.split(",")][:5]:
        try:
            resp = requests.get(
                "https://www.alphavantage.co/query",
                params={"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": api_key},
                headers=HEADERS, timeout=10,
            )
            quote = resp.json().get("Global Quote", {})
            if not quote:
                continue
            price  = float(quote.get("05. price", 0))
            change = float(quote.get("10. change percent", "0%").replace("%", ""))
            results.append({
                "type":   "stock",
                "symbol": symbol,
                "price":  price,
                "change": round(change, 2),
                "volume": quote.get("06. volume", ""),
            })
        except Exception as e:
            print(f"[Market] AV {symbol} error: {e}")
    return results


# ── Finnhub ───────────────────────────────────────────────────────────────────

def fetch_stocks_finnhub(symbols: str, api_key: str) -> List[Dict]:
    if not api_key:
        return []
    results = []
    for symbol in [s.strip() for s in symbols.split(",")][:10]:
        try:
            resp = requests.get(
                "https://finnhub.io/api/v1/quote",
                params={"symbol": symbol, "token": api_key},
                headers=HEADERS, timeout=8,
            )
            q = resp.json()
            if not q.get("c"):
                continue
            price  = q.get("c", 0)
            prev   = q.get("pc", price)
            change = round(((price - prev) / prev * 100) if prev else 0, 2)
            results.append({
                "type":   "stock",
                "symbol": symbol,
                "price":  price,
                "change": change,
                "high":   q.get("h"),
                "low":    q.get("l"),
            })
        except Exception as e:
            print(f"[Market] Finnhub {symbol} error: {e}")
    return results


# ── Main collector ────────────────────────────────────────────────────────────

def collect_market_pulse() -> Dict:
    cfg = get_market_config()
    ts  = datetime.now().isoformat()
    data = {"ts": ts, "crypto": [], "stocks": [], "forex": []}

    data["crypto"] = fetch_crypto(cfg["crypto_coins"])

    forex_targets = cfg["forex_pairs"].replace("/", ",").replace("USD", "").strip(",")
    data["forex"]  = fetch_forex("USD", forex_targets or "EUR,GBP,JPY")

    if cfg["finnhub_key"]:
        data["stocks"] = fetch_stocks_finnhub(cfg["stock_symbols"], cfg["finnhub_key"])
    elif cfg["alphavantage_key"]:
        data["stocks"] = fetch_stocks_av(cfg["stock_symbols"], cfg["alphavantage_key"])

    _save_snapshot(data)
    return data


# ── Formatting ────────────────────────────────────────────────────────────────

def _arrow(change: float) -> str:
    if change > 2:  return "🟢 ▲"
    if change > 0:  return "🟩 ↑"
    if change < -2: return "🔴 ▼"
    if change < 0:  return "🟥 ↓"
    return "⬜ —"


def format_pulse(data: Dict) -> str:
    if not data:
        return "📭 No data. Run /market first."

    ts = data.get("ts", "")
    try:
        ts = datetime.fromisoformat(ts).strftime("%d.%m.%Y %H:%M")
    except Exception:
        pass

    lines = [f"Updated: {ts}\n"]

    if data.get("crypto"):
        lines.append("🪙 Crypto")
        for c in data["crypto"]:
            arrow = _arrow(c.get("change", 0))
            lines.append(f"  {arrow} {c['symbol'].capitalize():<12} ${c['price']:>12,.2f}  {c.get('change', 0):+.2f}%")

    if data.get("stocks"):
        lines.append("\n📈 Stocks")
        for s in data["stocks"]:
            arrow = _arrow(s.get("change", 0))
            lines.append(f"  {arrow} {s['symbol']:<12} ${s['price']:>10,.2f}  {s.get('change', 0):+.2f}%")

    if data.get("forex"):
        lines.append("\n💱 Forex (USD →)")
        for f in data["forex"]:
            lines.append(f"  {f['pair']:<12} {f['rate']:.4f}")

    return "\n".join(lines)


# ── Alert signals ─────────────────────────────────────────────────────────────

def market_alert_signals(data: Dict) -> List[str]:
    signals = []
    if not data:
        return signals
    for c in data.get("crypto", []):
        change = abs(c.get("change", 0))
        if change >= 8:
            direction = "up" if c["change"] > 0 else "down"
            signals.append(f"🪙 {c['symbol'].capitalize()} {direction} {change:.1f}% in 24h")
    for s in data.get("stocks", []):
        change = abs(s.get("change", 0))
        if change >= 5:
            direction = "up" if s["change"] > 0 else "down"
            signals.append(f"📈 {s['symbol']} {direction} {change:.1f}%")
    return signals


# ── Context string for LLM ────────────────────────────────────────────────────

def market_context_for_llm(snapshots: int = 3) -> str:
    """Build a text summary of recent market snapshots for LLM prompts."""
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
