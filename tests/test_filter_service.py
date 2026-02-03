import pytest

from src.app.database import get_db
from src.app.services import filter_service


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
        articles = [
            ("guid-1", "Breaking News: Python 4.0 Released", "Major update to Python"),
            ("guid-2", "Sports Update: Football Championship", "The big game results"),
            ("guid-3", "Tech Review: New JavaScript Framework", "Yet another framework"),
            ("guid-4", "Python Tutorial for Beginners", "Learn Python basics"),
        ]

        article_ids = []
        for guid, title, summary in articles:
            cursor = db.execute("""
                INSERT INTO articles (feed_id, guid, title, summary, is_read, is_saved)
                VALUES (?, ?, ?, ?, 0, 0)
            """, (sample_feed, guid, title, summary))
            article_ids.append(cursor.lastrowid)

        db.commit()
        return article_ids


class TestCreateFilter:
    def test_create_filter_success(self, app):
        with app.app_context():
            f, error = filter_service.create_filter("Test Filter", r"\btest\b", "both")

            assert error is None
            assert f is not None
            assert f.name == "Test Filter"
            assert f.pattern == r"\btest\b"
            assert f.target == "both"
            assert f.is_active is True

    def test_create_filter_empty_name(self, app):
        with app.app_context():
            f, error = filter_service.create_filter("", "pattern", "both")

            assert f is None
            assert error == "Name is required"

    def test_create_filter_empty_pattern(self, app):
        with app.app_context():
            f, error = filter_service.create_filter("Name", "", "both")

            assert f is None
            assert error == "Pattern is required"

    def test_create_filter_invalid_target(self, app):
        with app.app_context():
            f, error = filter_service.create_filter("Name", "pattern", "invalid")

            assert f is None
            assert error == "Target must be 'title', 'summary', or 'both'"

    def test_create_filter_invalid_regex(self, app):
        with app.app_context():
            f, error = filter_service.create_filter("Name", "[invalid", "both")

            assert f is None
            assert error == "Invalid regex pattern"


class TestFilterMatching:
    def test_filter_applies_to_existing_articles(self, app, sample_articles):
        with app.app_context():
            f, _ = filter_service.create_filter("Python Filter", r"python", "both")

            db = get_db()
            matches = db.execute(
                "SELECT COUNT(*) as count FROM filter_matches WHERE filter_id = ?",
                (f.id,)
            ).fetchone()

            assert matches["count"] == 2

    def test_filter_marks_matched_as_read(self, app, sample_articles):
        with app.app_context():
            filter_service.create_filter("Python Filter", r"python", "both")

            db = get_db()
            read_articles = db.execute(
                "SELECT COUNT(*) as count FROM articles WHERE is_read = 1"
            ).fetchone()

            assert read_articles["count"] == 2

    def test_filter_title_only(self, app, sample_articles):
        with app.app_context():
            f, _ = filter_service.create_filter("Title Filter", r"breaking", "title")

            db = get_db()
            matches = db.execute(
                "SELECT COUNT(*) as count FROM filter_matches WHERE filter_id = ?",
                (f.id,)
            ).fetchone()

            assert matches["count"] == 1

    def test_filter_summary_only(self, app, sample_articles):
        with app.app_context():
            f, _ = filter_service.create_filter("Summary Filter", r"framework", "summary")

            db = get_db()
            matches = db.execute(
                "SELECT COUNT(*) as count FROM filter_matches WHERE filter_id = ?",
                (f.id,)
            ).fetchone()

            assert matches["count"] == 1

    def test_multiple_filters_match_new_article(self, app, sample_feed):
        with app.app_context():
            filter_service.create_filter("Filter 1", r"python", "both")
            filter_service.create_filter("Filter 2", r"breaking", "both")

            db = get_db()
            cursor = db.execute("""
                INSERT INTO articles (feed_id, guid, title, summary, is_read, is_saved)
                VALUES (?, 'new-guid', 'Breaking: Python News', 'Summary', 0, 0)
            """, (sample_feed,))
            db.commit()
            article_id = cursor.lastrowid

            filter_service.apply_filters_to_article(
                article_id, "Breaking: Python News", "Summary"
            )

            article_matches = db.execute("""
                SELECT article_id, COUNT(*) as match_count
                FROM filter_matches
                WHERE article_id = ?
                GROUP BY article_id
            """, (article_id,)).fetchall()

            assert len(article_matches) == 1
            assert article_matches[0]["match_count"] == 2

    def test_filter_skips_saved_articles(self, app, sample_feed):
        with app.app_context():
            db = get_db()
            db.execute("""
                INSERT INTO articles (feed_id, guid, title, summary, is_read, is_saved)
                VALUES (?, 'saved-guid', 'Python Saved Article', 'Saved', 0, 1)
            """, (sample_feed,))
            db.commit()

            f, _ = filter_service.create_filter("Python Filter", r"python", "both")

            matches = db.execute(
                "SELECT COUNT(*) as count FROM filter_matches WHERE filter_id = ?",
                (f.id,)
            ).fetchone()

            assert matches["count"] == 0

    def test_filter_skips_already_read_articles(self, app, sample_feed):
        with app.app_context():
            db = get_db()
            db.execute("""
                INSERT INTO articles (feed_id, guid, title, summary, is_read, is_saved)
                VALUES (?, 'read-guid', 'Python Read Article', 'Already read', 1, 0)
            """, (sample_feed,))
            db.commit()

            f, _ = filter_service.create_filter("Python Filter", r"python", "both")

            matches = db.execute(
                "SELECT COUNT(*) as count FROM filter_matches WHERE filter_id = ?",
                (f.id,)
            ).fetchone()

            assert matches["count"] == 0


class TestUpdateFilter:
    def test_update_filter_name(self, app):
        with app.app_context():
            f, _ = filter_service.create_filter("Original", "pattern", "both")
            updated, error = filter_service.update_filter(f.id, name="Updated")

            assert error is None
            assert updated.name == "Updated"

    def test_update_filter_pattern_reapplies(self, app, sample_articles):
        with app.app_context():
            f, _ = filter_service.create_filter("Filter", r"nonexistent", "both")

            db = get_db()
            initial_matches = db.execute(
                "SELECT COUNT(*) as count FROM filter_matches WHERE filter_id = ?",
                (f.id,)
            ).fetchone()["count"]

            db.execute("UPDATE articles SET is_read = 0")
            db.commit()

            filter_service.update_filter(f.id, pattern=r"python")

            new_matches = db.execute(
                "SELECT COUNT(*) as count FROM filter_matches WHERE filter_id = ?",
                (f.id,)
            ).fetchone()["count"]

            assert initial_matches == 0
            assert new_matches == 2

    def test_update_filter_toggle_active(self, app):
        with app.app_context():
            f, _ = filter_service.create_filter("Filter", "pattern", "both")

            updated, _ = filter_service.update_filter(f.id, is_active=False)
            assert updated.is_active is False

            updated, _ = filter_service.update_filter(f.id, is_active=True)
            assert updated.is_active is True


class TestDeleteFilter:
    def test_delete_filter_success(self, app):
        with app.app_context():
            f, _ = filter_service.create_filter("Filter", "pattern", "both")
            result = filter_service.delete_filter(f.id)

            assert result is True
            assert filter_service.get_filter_by_id(f.id) is None

    def test_delete_filter_removes_matches(self, app, sample_articles):
        with app.app_context():
            f, _ = filter_service.create_filter("Python", r"python", "both")
            filter_id = f.id

            db = get_db()
            matches_before = db.execute(
                "SELECT COUNT(*) as count FROM filter_matches WHERE filter_id = ?",
                (filter_id,)
            ).fetchone()["count"]

            filter_service.delete_filter(filter_id)

            matches_after = db.execute(
                "SELECT COUNT(*) as count FROM filter_matches WHERE filter_id = ?",
                (filter_id,)
            ).fetchone()["count"]

            assert matches_before > 0
            assert matches_after == 0


class TestGetFilteredArticles:
    def test_get_filtered_by_rule(self, app, sample_articles):
        with app.app_context():
            filter_service.create_filter("Python", r"python", "both")
            filter_service.create_filter("Sports", r"sports|football", "both")

            grouped = filter_service.get_filtered_articles_by_rule()

            assert len(grouped) == 2

            python_entry = [entry for entry in grouped if entry[0].name == "Python"][0]
            sports_entry = [entry for entry in grouped if entry[0].name == "Sports"][0]

            assert len(python_entry[1]) == 2
            assert len(sports_entry[1]) == 1

    def test_get_total_filtered_count(self, app, sample_articles):
        with app.app_context():
            filter_service.create_filter("Python", r"python", "both")
            filter_service.create_filter("Sports", r"sports|football", "both")

            total = filter_service.get_total_filtered_count()

            assert total == 3


class TestRegexValidation:
    def test_valid_regex(self, app):
        with app.app_context():
            assert filter_service.is_valid_regex(r"\btest\b") is True
            assert filter_service.is_valid_regex(r"foo|bar") is True
            assert filter_service.is_valid_regex(r"^start") is True

    def test_invalid_regex(self, app):
        with app.app_context():
            assert filter_service.is_valid_regex(r"[invalid") is False
            assert filter_service.is_valid_regex(r"(unclosed") is False
            assert filter_service.is_valid_regex(r"*invalid") is False
