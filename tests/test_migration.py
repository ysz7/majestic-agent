"""Quick smoke test for ResearchDB score migration."""
import tempfile, os, sqlite3

def test_migration():
    from majestic.tools.research.db import ResearchDB
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "old.db")
        # Simulate old DB without score column
        conn = sqlite3.connect(db_path)
        conn.execute(
            "CREATE TABLE articles ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, url_hash TEXT UNIQUE NOT NULL, "
            "url TEXT, title TEXT NOT NULL, summary TEXT, source TEXT, "
            "category TEXT, date TEXT, fetched_at TEXT DEFAULT (date('now')))"
        )
        conn.commit()
        conn.close()

        db = ResearchDB(db_path)
        new, skipped = db.insert_articles([
            {"title": "Test", "source": "Reuters", "category": "breaking",
             "date": "2026-05-27", "url": "http://x1", "summary": "test"}
        ])
        assert len(new) == 1
        results = db.get_articles(days=365)
        assert results[0]["score"] > 0.0, f"Expected score > 0, got {results[0]['score']}"
        db.close()
        print(f"Migration OK — score={results[0]['score']}")

if __name__ == "__main__":
    test_migration()
