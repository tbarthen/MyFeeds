from unittest.mock import patch, MagicMock

import pytest

from src.app.services import feed_service


class MockFeedParserDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self


def make_mock_parsed_feed(title="Test Feed", link="https://example.com", entries=None):
    if entries is None:
        entries = [{
            "id": "entry-1",
            "title": "Test Article",
            "summary": "This is a test summary",
            "link": "https://example.com/article-1",
            "published_parsed": (2024, 1, 15, 12, 0, 0, 0, 0, 0)
        }]

    feed_data = MockFeedParserDict()
    feed_data["feed"] = {"title": title, "link": link}
    feed_data["entries"] = [MockFeedParserDict(e) for e in entries]
    feed_data["bozo"] = False
    return feed_data


@pytest.fixture
def mock_requests_get():
    with patch("src.app.services.feed_service.requests.get") as mock:
        mock.return_value = MagicMock(content=b"<xml></xml>")
        yield mock


@pytest.fixture
def mock_feedparser():
    with patch("src.app.services.feed_service.feedparser.parse") as mock:
        mock.return_value = make_mock_parsed_feed()
        yield mock


class TestAddFeed:
    def test_add_feed_success(self, app, mock_requests_get, mock_feedparser):
        with app.app_context():
            feed, error = feed_service.add_feed("https://example.com/feed.xml")

            assert error is None
            assert feed is not None
            assert feed.title == "Test Feed"
            assert feed.url == "https://example.com/feed.xml"

    def test_add_feed_duplicate_rejected(self, app, mock_requests_get, mock_feedparser):
        with app.app_context():
            feed_service.add_feed("https://example.com/feed.xml")
            feed, error = feed_service.add_feed("https://example.com/feed.xml")

            assert feed is None
            assert error == "Feed already exists"

    def test_add_feed_saves_articles(self, app, mock_requests_get, mock_feedparser):
        with app.app_context():
            from src.app.services import article_service

            feed_service.add_feed("https://example.com/feed.xml")
            articles = article_service.get_articles()

            assert len(articles) == 1
            assert articles[0].title == "Test Article"


class TestGetFeeds:
    def test_get_all_feeds_empty(self, app):
        with app.app_context():
            feeds = feed_service.get_all_feeds()
            assert feeds == []

    def test_get_all_feeds_returns_feeds(self, app, mock_requests_get, mock_feedparser):
        with app.app_context():
            feed_service.add_feed("https://example.com/feed.xml")
            feeds = feed_service.get_all_feeds()

            assert len(feeds) == 1
            assert feeds[0].title == "Test Feed"

    def test_get_feed_by_id(self, app, mock_requests_get, mock_feedparser):
        with app.app_context():
            added_feed, _ = feed_service.add_feed("https://example.com/feed.xml")
            feed = feed_service.get_feed_by_id(added_feed.id)

            assert feed is not None
            assert feed.id == added_feed.id

    def test_get_feed_by_id_not_found(self, app):
        with app.app_context():
            feed = feed_service.get_feed_by_id(999)
            assert feed is None


class TestDeleteFeed:
    def test_delete_feed_success(self, app, mock_requests_get, mock_feedparser):
        with app.app_context():
            added_feed, _ = feed_service.add_feed("https://example.com/feed.xml")
            result = feed_service.delete_feed(added_feed.id)

            assert result is True
            assert feed_service.get_feed_by_id(added_feed.id) is None

    def test_delete_feed_not_found(self, app):
        with app.app_context():
            result = feed_service.delete_feed(999)
            assert result is False


class TestRefreshFeed:
    def test_refresh_feed_adds_new_articles(self, app, mock_requests_get, mock_feedparser):
        with app.app_context():
            from src.app.services import article_service

            added_feed, _ = feed_service.add_feed("https://example.com/feed.xml")

            mock_feedparser.return_value = make_mock_parsed_feed(entries=[
                {"id": "entry-1", "title": "Test Article", "link": "https://example.com/1"},
                {"id": "entry-2", "title": "New Article", "link": "https://example.com/2"},
            ])

            new_count, error = feed_service.refresh_feed(added_feed.id)

            assert error is None
            assert new_count == 1

            articles = article_service.get_articles(feed_id=added_feed.id)
            assert len(articles) == 2

    def test_refresh_feed_not_found(self, app):
        with app.app_context():
            new_count, error = feed_service.refresh_feed(999)

            assert new_count == 0
            assert error == "Feed not found"
