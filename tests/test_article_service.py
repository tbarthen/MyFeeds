import pytest

from src.app.database import get_db
from src.app.services import article_service


@pytest.fixture
def sample_feed(app):
    with app.app_context():
        db = get_db()
        cursor = db.execute(
            "INSERT INTO feeds (url, title) VALUES (?, ?)",
            ("https://example.com/feed.xml", "Test Feed")
        )
        db.commit()
        return cursor.lastrowid


@pytest.fixture
def sample_articles(app, sample_feed):
    with app.app_context():
        db = get_db()
        article_ids = []

        articles = [
            ("guid-1", "Article One", "Summary one", False, False),
            ("guid-2", "Article Two", "Summary two", True, False),
            ("guid-3", "Article Three", "Summary three", False, True),
        ]

        for guid, title, summary, is_read, is_saved in articles:
            cursor = db.execute("""
                INSERT INTO articles (feed_id, guid, title, summary, is_read, is_saved)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (sample_feed, guid, title, summary, is_read, is_saved))
            article_ids.append(cursor.lastrowid)

        db.commit()
        return article_ids


class TestGetArticles:
    def test_get_all_articles(self, app, sample_articles):
        with app.app_context():
            articles = article_service.get_articles()
            assert len(articles) == 3

    def test_get_unread_articles(self, app, sample_articles):
        with app.app_context():
            articles = article_service.get_articles(unread_only=True)
            assert len(articles) == 2
            assert all(not a.is_read for a in articles)

    def test_get_saved_articles(self, app, sample_articles):
        with app.app_context():
            articles = article_service.get_articles(saved_only=True)
            assert len(articles) == 1
            assert articles[0].is_saved

    def test_get_articles_by_feed(self, app, sample_feed, sample_articles):
        with app.app_context():
            articles = article_service.get_articles(feed_id=sample_feed)
            assert len(articles) == 3

    def test_get_article_by_id(self, app, sample_articles):
        with app.app_context():
            article = article_service.get_article_by_id(sample_articles[0])
            assert article is not None
            assert article.title == "Article One"


class TestMarkRead:
    def test_mark_article_read(self, app, sample_articles):
        with app.app_context():
            result = article_service.mark_article_read(sample_articles[0], is_read=True)
            assert result is True

            article = article_service.get_article_by_id(sample_articles[0])
            assert article.is_read is True

    def test_mark_article_unread(self, app, sample_articles):
        with app.app_context():
            result = article_service.mark_article_read(sample_articles[1], is_read=False)
            assert result is True

            article = article_service.get_article_by_id(sample_articles[1])
            assert article.is_read is False

    def test_mark_all_read(self, app, sample_feed, sample_articles):
        with app.app_context():
            count = article_service.mark_all_read()
            assert count == 2

            articles = article_service.get_articles(unread_only=True)
            assert len(articles) == 0

    def test_mark_all_read_in_feed(self, app, sample_feed, sample_articles):
        with app.app_context():
            count = article_service.mark_all_read(feed_id=sample_feed)
            assert count == 2

    def test_mark_all_read_by_ids(self, app, sample_articles):
        with app.app_context():
            ids_to_mark = [sample_articles[0]]
            count = article_service.mark_all_read(article_ids=ids_to_mark)
            assert count == 1

            marked = article_service.get_article_by_id(sample_articles[0])
            assert marked.is_read is True

            untouched = article_service.get_article_by_id(sample_articles[2])
            assert untouched.is_read is False

    def test_mark_all_read_by_ids_skips_already_read(self, app, sample_articles):
        with app.app_context():
            count = article_service.mark_all_read(
                article_ids=[sample_articles[1]]
            )
            assert count == 0


class TestToggleSaved:
    def test_toggle_saved_on(self, app, sample_articles):
        with app.app_context():
            result = article_service.toggle_saved(sample_articles[0])
            assert result is True

            article = article_service.get_article_by_id(sample_articles[0])
            assert article.is_saved is True

    def test_toggle_saved_off(self, app, sample_articles):
        with app.app_context():
            result = article_service.toggle_saved(sample_articles[2])
            assert result is False

            article = article_service.get_article_by_id(sample_articles[2])
            assert article.is_saved is False

    def test_toggle_saved_not_found(self, app):
        with app.app_context():
            result = article_service.toggle_saved(999)
            assert result is None


class TestUnreadCount:
    def test_get_unread_count_all(self, app, sample_articles):
        with app.app_context():
            count = article_service.get_unread_count()
            assert count == 2

    def test_get_unread_count_by_feed(self, app, sample_feed, sample_articles):
        with app.app_context():
            count = article_service.get_unread_count(feed_id=sample_feed)
            assert count == 2


class TestCleanupOldArticles:
    def _insert(self, db, feed_id, guid, is_read, is_saved, age_days):
        db.execute(
            "INSERT INTO articles (feed_id, guid, title, is_read, is_saved, created_at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now', ?))",
            (feed_id, guid, guid, is_read, is_saved, f"-{age_days} days")
        )

    def test_deletes_old_read_unsaved(self, app, sample_feed):
        with app.app_context():
            db = get_db()
            self._insert(db, sample_feed, "old-read", is_read=1, is_saved=0, age_days=8)
            db.commit()

            assert article_service.cleanup_old_articles(retention_days=7) == 1
            assert article_service.get_articles() == []

    def test_keeps_old_unread_unsaved(self, app, sample_feed):
        with app.app_context():
            db = get_db()
            self._insert(db, sample_feed, "old-unread", is_read=0, is_saved=0, age_days=8)
            db.commit()

            assert article_service.cleanup_old_articles(retention_days=7) == 0
            assert len(article_service.get_articles()) == 1

    def test_keeps_saved_regardless_of_age(self, app, sample_feed):
        with app.app_context():
            db = get_db()
            self._insert(db, sample_feed, "ancient-saved", is_read=1, is_saved=1, age_days=365)
            db.commit()

            assert article_service.cleanup_old_articles(retention_days=7) == 0
            remaining = article_service.get_articles(saved_only=True)
            assert len(remaining) == 1

    def test_keeps_recent_articles(self, app, sample_feed):
        with app.app_context():
            db = get_db()
            self._insert(db, sample_feed, "recent-read", is_read=1, is_saved=0, age_days=2)
            self._insert(db, sample_feed, "recent-unread", is_read=0, is_saved=0, age_days=6)
            db.commit()

            assert article_service.cleanup_old_articles(retention_days=7) == 0
            assert len(article_service.get_articles()) == 2

    def test_mixed_set(self, app, sample_feed):
        with app.app_context():
            db = get_db()
            self._insert(db, sample_feed, "old-read", is_read=1, is_saved=0, age_days=30)
            self._insert(db, sample_feed, "old-unread", is_read=0, is_saved=0, age_days=10)
            self._insert(db, sample_feed, "old-saved", is_read=1, is_saved=1, age_days=30)
            self._insert(db, sample_feed, "recent", is_read=1, is_saved=0, age_days=1)
            db.commit()

            assert article_service.cleanup_old_articles(retention_days=7) == 1
            remaining = sorted(a.title for a in article_service.get_articles())
            assert remaining == ["old-saved", "old-unread", "recent"]

    def test_cascades_to_filter_matches(self, app, sample_feed):
        with app.app_context():
            db = get_db()
            self._insert(db, sample_feed, "old-filtered", is_read=1, is_saved=0, age_days=14)
            article_id = db.execute(
                "SELECT id FROM articles WHERE guid = 'old-filtered'"
            ).fetchone()["id"]
            db.execute(
                "INSERT INTO filters (name, pattern, target) VALUES ('t', 'x', 'both')"
            )
            filter_id = db.execute("SELECT id FROM filters").fetchone()["id"]
            db.execute(
                "INSERT INTO filter_matches (article_id, filter_id) VALUES (?, ?)",
                (article_id, filter_id)
            )
            db.commit()

            assert article_service.cleanup_old_articles(retention_days=7) == 1
            orphans = db.execute(
                "SELECT COUNT(*) AS n FROM filter_matches WHERE article_id = ?",
                (article_id,)
            ).fetchone()["n"]
            assert orphans == 0

    def _read_at(self, db, guid):
        return db.execute(
            "SELECT read_at FROM articles WHERE guid = ?", (guid,)
        ).fetchone()["read_at"]

    def _id(self, db, guid):
        return db.execute("SELECT id FROM articles WHERE guid = ?", (guid,)).fetchone()["id"]

    def test_keeps_old_article_that_was_just_read(self, app, sample_feed):
        with app.app_context():
            db = get_db()
            self._insert(db, sample_feed, "old-just-read", is_read=0, is_saved=0, age_days=30)
            db.commit()

            article_service.mark_article_read(self._id(db, "old-just-read"), is_read=True)

            assert article_service.cleanup_old_articles(retention_days=7) == 0

    def test_keeps_old_articles_after_mark_all_read(self, app, sample_feed):
        with app.app_context():
            db = get_db()
            self._insert(db, sample_feed, "old-a", is_read=0, is_saved=0, age_days=30)
            self._insert(db, sample_feed, "old-b", is_read=0, is_saved=0, age_days=30)
            db.commit()

            article_service.mark_all_read()

            assert article_service.cleanup_old_articles(retention_days=7) == 0

    def test_deletes_article_read_longer_ago_than_retention(self, app, sample_feed):
        with app.app_context():
            db = get_db()
            self._insert(db, sample_feed, "read-long-ago", is_read=1, is_saved=0, age_days=30)
            db.execute(
                "UPDATE articles SET read_at = datetime('now', '-8 days') WHERE guid = 'read-long-ago'"
            )
            db.commit()

            assert article_service.cleanup_old_articles(retention_days=7) == 1

    def test_mark_unread_clears_read_time(self, app, sample_feed):
        with app.app_context():
            db = get_db()
            self._insert(db, sample_feed, "toggled", is_read=0, is_saved=0, age_days=1)
            db.commit()
            article_id = self._id(db, "toggled")

            article_service.mark_article_read(article_id, is_read=True)
            assert self._read_at(db, "toggled") is not None

            article_service.mark_article_read(article_id, is_read=False)
            assert self._read_at(db, "toggled") is None


class TestReadAtMigration:
    def test_upgrade_restarts_retention_for_already_read_articles(self, app, sample_feed):
        from src.app.database import _add_read_at_column

        with app.app_context():
            db = get_db()
            db.execute("ALTER TABLE articles DROP COLUMN read_at")
            db.execute(
                "INSERT INTO articles (feed_id, guid, title, is_read, created_at) "
                "VALUES (?, 'legacy-read', 'legacy-read', 1, datetime('now', '-30 days'))",
                (sample_feed,)
            )
            db.execute(
                "INSERT INTO articles (feed_id, guid, title, is_read, created_at) "
                "VALUES (?, 'legacy-unread', 'legacy-unread', 0, datetime('now', '-30 days'))",
                (sample_feed,)
            )
            db.commit()

            _add_read_at_column(db)

            rows = {
                row["guid"]: row["read_at"]
                for row in db.execute("SELECT guid, read_at FROM articles").fetchall()
            }
            assert rows["legacy-read"] is not None
            assert rows["legacy-unread"] is None
            assert article_service.cleanup_old_articles(retention_days=7) == 0


class TestSearchArticles:
    @pytest.fixture
    def many_articles(self, app, sample_feed):
        with app.app_context():
            db = get_db()
            for i in range(70):
                db.execute(
                    "INSERT INTO articles (feed_id, guid, title, summary, is_read, published_at) "
                    "VALUES (?, ?, ?, ?, 1, ?)",
                    (sample_feed, f"bulk-{i}", f"Filler {i}", "Nothing here",
                     f"2026-11-{10 + i // 10:02d}T{i % 10:02d}:00:00")
                )
            db.execute(
                "INSERT INTO articles (feed_id, guid, title, summary, is_read, published_at) "
                "VALUES (?, ?, ?, ?, 1, ?)",
                (sample_feed, "old", "Google Wallet home key", "Unlock your door",
                 "2026-11-01T00:00:00")
            )
            db.commit()

    def test_finds_read_article_beyond_page_limit(self, app, many_articles):
        with app.app_context():
            assert "Google Wallet home key" not in [a.title for a in article_service.get_articles()]
            results = article_service.get_articles(unread_only=True, search="wallet")
            assert [a.title for a in results] == ["Google Wallet home key"]

    def test_matches_summary(self, app, many_articles):
        with app.app_context():
            results = article_service.get_articles(search="UNLOCK")
            assert [a.title for a in results] == ["Google Wallet home key"]

    def test_wildcards_are_literal(self, app, sample_articles):
        with app.app_context():
            assert article_service.get_articles(search="%") == []
            assert article_service.get_articles(search="_") == []

    def test_blank_search_is_ignored(self, app, sample_articles):
        with app.app_context():
            assert len(article_service.get_articles(unread_only=True, search="   ")) == 2

    def test_search_respects_saved_scope(self, app, sample_articles):
        with app.app_context():
            results = article_service.get_articles(saved_only=True, search="Article")
            assert [a.title for a in results] == ["Article Three"]

    def test_normalize_search_caps_length(self):
        long_query = "x" * (article_service.MAX_SEARCH_LENGTH + 50)
        assert len(article_service.normalize_search(long_query)) == article_service.MAX_SEARCH_LENGTH
        assert article_service.normalize_search(None) == ""


class TestSearchRoutes:
    def test_index_search_includes_read_articles(self, client, sample_articles):
        body = client.get("/?q=two").get_data(as_text=True)
        assert "Article Two" in body
        assert "Article One" not in body
        assert "1 result for" in body

    def test_saved_search(self, client, sample_articles):
        body = client.get("/saved?q=three").get_data(as_text=True)
        assert "Article Three" in body
        assert "in all saved articles" in body

    def test_no_results(self, client, sample_articles):
        body = client.get("/?q=zzz").get_data(as_text=True)
        assert "0 results for" in body

    def test_search_term_is_escaped(self, client, sample_articles):
        body = client.get("/?q=<b>x</b>").get_data(as_text=True)
        assert "<b>x</b>" not in body
