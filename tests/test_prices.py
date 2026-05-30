"""Smoke tests for market price storage and formatting."""
import tempfile, os


def test_insert_and_get_prices():
    from majestic.tools.research.db import ResearchDB

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        db = ResearchDB(os.path.join(d, "research.db"))

        sample = [
            {"symbol": "BTC", "name": "Bitcoin", "asset_class": "crypto",
             "price": 67420.0, "change_24h": 2.4, "change_7d": 8.1,
             "market_cap": 1_320_000_000_000, "volume_24h": 35_000_000_000, "currency": "USD"},
            {"symbol": "ETH", "name": "Ethereum", "asset_class": "crypto",
             "price": 3240.0, "change_24h": 1.8, "change_7d": 5.2,
             "market_cap": 390_000_000_000, "volume_24h": 18_000_000_000, "currency": "USD"},
            {"symbol": "^SPX", "name": "S&P 500", "asset_class": "index",
             "price": 4892.0, "change_24h": 0.3, "change_7d": None,
             "market_cap": None, "volume_24h": None, "currency": "USD"},
            {"symbol": "GC=F", "name": "Gold", "asset_class": "commodity",
             "price": 2340.0, "change_24h": -0.1, "change_7d": None,
             "market_cap": None, "volume_24h": None, "currency": "USD"},
        ]

        n = db.insert_prices(sample)
        assert n == 4, f"Expected 4 inserted, got {n}"

        prices, ts = db.get_latest_prices()
        assert len(prices) == 4
        assert ts != ""

        symbols = {p["symbol"] for p in prices}
        assert "BTC" in symbols
        assert "^SPX" in symbols

        db.close()
        print(f"insert/get test passed: {len(prices)} prices, ts={ts[:16]}")


def test_prices_corpus_format():
    from majestic.tools.research.prices import format_prices_for_corpus, format_prices_for_display

    sample = [
        {"symbol": "BTC", "name": "Bitcoin", "asset_class": "crypto",
         "price": 67420.0, "change_24h": 2.4, "change_7d": 8.1,
         "market_cap": 1_320_000_000_000, "volume_24h": None, "currency": "USD"},
        {"symbol": "^SPX", "name": "S&P 500", "asset_class": "index",
         "price": 4892.0, "change_24h": 0.3, "change_7d": None,
         "market_cap": None, "volume_24h": None, "currency": "USD"},
    ]

    corpus = format_prices_for_corpus(sample, "2026-05-30T14:23:00")
    assert "LIVE MARKET DATA" in corpus
    assert "BTC" in corpus
    assert "S&P 500" in corpus
    assert "+2.4%" in corpus

    display = format_prices_for_display(sample)
    assert "BTC" in display
    assert "S&P 500" in display

    print("format tests passed!")
    print("Corpus block:\n", corpus)


if __name__ == "__main__":
    test_insert_and_get_prices()
    test_prices_corpus_format()
    print("All price tests passed!")
