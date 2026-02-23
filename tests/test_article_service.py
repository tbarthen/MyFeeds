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
