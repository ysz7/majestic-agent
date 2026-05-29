"""Phase 7 smoke tests: pains DB schema migration + trending detection."""
import tempfile, os, time


def test_pains_new_fields():
    from majestic.tools.pains.db import PainsDB

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        db = PainsDB(os.path.join(d, "pains.db"))

        db.insert_pains([
            {"pain_text": "No automated B2B onboarding for teams >10", "domain": "b2b",
             "intensity": "HIGH", "willingness_to_pay": True},
            {"pain_text": "Docs keep going out of sync with code", "domain": "devtools",
             "intensity": "MEDIUM", "willingness_to_pay": False},
            {"pain_text": "Minor UI lag on mobile", "domain": "devtools",
             "intensity": "LOW", "willingness_to_pay": False},
        ])

        pains = db.get_pains(days=1)
        assert len(pains) == 3

        high = [p for p in pains if p["intensity"] == "HIGH"]
        assert len(high) == 1
        assert high[0]["willingness_to_pay"] == 1  # stored as int

        db.close()
        print("New fields test passed!")


def test_pains_migration_from_old_schema():
    """Simulate an existing DB without intensity/wtp columns."""
    import sqlite3
    from majestic.tools.pains.db import PainsDB

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        db_path = os.path.join(d, "pains.db")

        # Create old-schema DB manually
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE raw_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_hash TEXT UNIQUE NOT NULL,
                url TEXT, title TEXT NOT NULL,
                summary TEXT, source TEXT, date TEXT,
                fetched_at TEXT DEFAULT (date('now'))
            );
            CREATE TABLE pains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pain_text TEXT NOT NULL,
                domain TEXT,
                source TEXT, url TEXT, date TEXT,
                fetched_at TEXT DEFAULT (date('now'))
            );
            INSERT INTO pains (pain_text, domain) VALUES ('Old pain', 'b2b');
        """)
        conn.commit()
        conn.close()

        # Open with new PainsDB — should migrate
        db = PainsDB(db_path)
        pains = db.get_pains(days=365)
        assert len(pains) == 1
        assert pains[0]["intensity"] == "MEDIUM"   # default from migration
        assert pains[0]["willingness_to_pay"] == 0  # default from migration
        db.close()
        print("Migration test passed!")


def test_trending_domains():
    from majestic.tools.pains.db import PainsDB

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        db = PainsDB(os.path.join(d, "pains.db"))

        # Insert "old" posts by manipulating fetched_at
        db._conn.execute(
            "INSERT INTO pains (pain_text, domain, fetched_at) VALUES (?,?,date('now','-10 days'))",
            ("Old b2b pain", "b2b"),
        )
        db._conn.execute(
            "INSERT INTO pains (pain_text, domain, fetched_at) VALUES (?,?,date('now','-10 days'))",
            ("Old devtools pain", "devtools"),
        )
        db._conn.commit()

        # Insert "recent" posts (today)
        db.insert_pains([
            {"pain_text": "New b2b pain 1", "domain": "b2b"},
            {"pain_text": "New b2b pain 2", "domain": "b2b"},
            {"pain_text": "New b2b pain 3", "domain": "b2b"},
        ])

        trends = db.get_trending_domains(current_days=7, compare_days=14)
        # b2b: 3 now vs 1 before → +200%; devtools: 0 now vs 1 before (not in result)
        b2b = next((t for t in trends if t["domain"] == "b2b"), None)
        assert b2b is not None
        assert b2b["delta_pct"] == 200
        assert b2b["current"] == 3

        db.close()
        print(f"Trending test passed! trends={trends}")


if __name__ == "__main__":
    test_pains_new_fields()
    test_pains_migration_from_old_schema()
    test_trending_domains()
    print("All Phase 7 pains tests passed!")
