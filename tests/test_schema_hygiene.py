"""Phase 10 — schema hygiene: domain taxonomy, schema_version, domain backfill."""
import os
import tempfile


def test_normalize_domain():
    from majestic.tools.pains.taxonomy import normalize_domain, CANONICAL_DOMAINS

    # aliases → canonical
    assert normalize_domain("webdev") == "web"
    assert normalize_domain("FinTech") == "finance"
    assert normalize_domain("  SaaS ") == "b2b"
    assert normalize_domain("no-code") == "nocode"
    # canonical passes through
    assert normalize_domain("finance") == "finance"
    assert normalize_domain("productivity") == "productivity"
    # unknown / empty → other
    assert normalize_domain("zzz-unknown") == "other"
    assert normalize_domain("") == "other"
    assert normalize_domain(None) == "other"
    # every result is canonical
    for raw in ["webdev", "x", "fintech", None, "design"]:
        assert normalize_domain(raw) in CANONICAL_DOMAINS


def test_pains_schema_version_and_domain_normalized_on_insert():
    from majestic.tools.pains.db import PainsDB, SCHEMA_VERSION

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        db = PainsDB(os.path.join(d, "pains.db"))

        # schema_version column exists
        cols = db.table_columns("pains")
        assert "schema_version" in cols

        # domain is normalized on insert; schema_version stamped
        db.insert_pains([
            {"pain_text": "x", "domain": "webdev", "intensity": "HIGH", "wtp": True},
            {"pain_text": "y", "domain": "FinTech"},
        ])
        rows = {r["pain_text"]: r for r in db.get_pains(days=3650)}
        assert rows["x"]["domain"] == "web"
        assert rows["y"]["domain"] == "finance"

        sv = {r[0] for r in db._conn.execute("SELECT DISTINCT schema_version FROM pains")}
        assert sv == {SCHEMA_VERSION}
        db.close()


def test_normalize_existing_domains_backfill_idempotent():
    from majestic.tools.pains.db import PainsDB

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        db = PainsDB(os.path.join(d, "pains.db"))
        # write a non-canonical domain directly (bypass insert normalization)
        db._conn.execute(
            "INSERT INTO pains (pain_text, domain) VALUES (?, ?)", ("legacy", "webdev")
        )
        db._conn.commit()

        changed = db.normalize_existing_domains()
        assert changed == 1
        row = db._conn.execute(
            "SELECT domain FROM pains WHERE pain_text='legacy'"
        ).fetchone()
        assert row[0] == "web"

        # second run is a no-op
        assert db.normalize_existing_domains() == 0
        db.close()


def test_research_articles_schema_version():
    from majestic.tools.research.db import ResearchDB

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        db = ResearchDB(os.path.join(d, "research.db"))
        assert "schema_version" in db.table_columns("articles")
        db.close()


if __name__ == "__main__":
    test_normalize_domain()
    test_pains_schema_version_and_domain_normalized_on_insert()
    test_normalize_existing_domains_backfill_idempotent()
    test_research_articles_schema_version()
    print("All schema hygiene tests passed!")
