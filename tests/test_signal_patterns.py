"""Smoke test for signal patterns save + FTS5 recall."""
import tempfile, os

def test_signal_patterns():
    from majestic.memory.lessons import LessonsStore

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        ls = LessonsStore(os.path.join(d, "lessons.db"))

        ls.save_signal_pattern(
            ["Fed rate hike", "EM debt stress", "copper prices falling", "dollar strengthening"],
            "## SECTION 2\n**EM currency devaluation** — **72%**\n- Causal chain: ...",
            72.0,
        )
        ls.save_signal_pattern(
            ["AI model release", "tech layoffs", "GPU shortage", "VC funding drop"],
            "## SECTION 2\n**Tech sector contraction** — **65%**\n- Causal chain: ...",
            65.0,
        )

        # OR query: "rate" should match "Fed rate hike"
        r1 = ls.search_signal_patterns("Federal Reserve rate dollar copper", limit=3)
        assert len(r1) >= 1, f"Expected >=1 result, got {len(r1)}"
        assert "rate" in r1[0]["signals_text"] or "copper" in r1[0]["signals_text"]
        print(f"Fed pattern found: {r1[0]['signals_text'][:60]} conf={r1[0]['avg_confidence']}")

        # Should find AI pattern
        r2 = ls.search_signal_patterns("artificial intelligence model GPU startup", limit=3)
        assert len(r2) >= 1, f"Expected >=1 result, got {len(r2)}"
        print(f"AI pattern found: {r2[0]['signals_text'][:60]} conf={r2[0]['avg_confidence']}")

        ls._conn.close()
        print("All signal pattern tests passed!")

if __name__ == "__main__":
    test_signal_patterns()
