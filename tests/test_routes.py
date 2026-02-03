from unittest.mock import patch, MagicMock

import pytest

from src.app.database import get_db


class MockFeedParserDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self


@pytest.fixture
def mock_feed_fetch():
    with patch("src.app.services.feed_service.requests.get") as mock_req, \
         patch("src.app.services.feed_service.feedparser.parse") as mock_parse:
        mock_req.return_value = MagicMock(content=b"<xml></xml>")

        parsed = MockFeedParserDict()
        parsed["feed"] = {"title": "Test Feed", "link": "https://example.com"}
        parsed["entries"] = [MockFeedParserDict({
            "id": "entry-1",
            "title": "Test Article",
            "summary": "Test summary",
            "link": "https://example.com/article"
        })]
        parsed["bozo"] = False
        mock_parse.return_value = parsed

        yield mock_req, mock_parse


class TestIndexRoute:
    def test_index_empty(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert b"MyFeeds" in response.data

    def test_index_with_feeds(self, client, app, mock_feed_fetch):
        client.post("/feeds/add", data={"url": "https://example.com/feed.xml"})

        response = client.get("/")
        assert response.status_code == 200
        assert b"Test Feed" in response.data

    def test_index_filter_by_feed(self, client, app, mock_feed_fetch):
        client.post("/feeds/add", data={"url": "https://example.com/feed.xml"})

        with app.app_context():
            db = get_db()
            feed = db.execute("SELECT id FROM feeds").fetchone()

        response = client.get(f"/?feed_id={feed['id']}")
        assert response.status_code == 200

    def test_index_unread_filter(self, client):
        response = client.get("/?unread=1")
        assert response.status_code == 200


class TestFeedRoutes:
    def test_add_feed(self, client, mock_feed_fetch):
        response = client.post(
            "/feeds/add",
            data={"url": "https://example.com/feed.xml"},
            follow_redirects=True
        )
        assert response.status_code == 200
        assert b"Test Feed" in response.data

    def test_add_feed_empty_url(self, client):
        response = client.post("/feeds/add", data={"url": ""}, follow_redirects=True)
        assert response.status_code == 200

    def test_delete_feed(self, client, app, mock_feed_fetch):
        client.post("/feeds/add", data={"url": "https://example.com/feed.xml"})

        with app.app_context():
            db = get_db()
            feed = db.execute("SELECT id FROM feeds").fetchone()

        response = client.post(
            f"/feeds/{feed['id']}/delete",
            follow_redirects=True
        )
        assert response.status_code == 200

    def test_refresh_feed(self, client, app, mock_feed_fetch):
        client.post("/feeds/add", data={"url": "https://example.com/feed.xml"})

        with app.app_context():
            db = get_db()
            feed = db.execute("SELECT id FROM feeds").fetchone()

        response = client.post(
            f"/feeds/{feed['id']}/refresh",
            follow_redirects=True
        )
        assert response.status_code == 200

    def test_refresh_all_feeds(self, client, mock_feed_fetch):
        client.post("/feeds/add", data={"url": "https://example.com/feed.xml"})

        response = client.post("/feeds/refresh-all", follow_redirects=True)
        assert response.status_code == 200


class TestArticleRoutes:
    @pytest.fixture
    def article_id(self, client, app, mock_feed_fetch):
        client.post("/feeds/add", data={"url": "https://example.com/feed.xml"})

        with app.app_context():
            db = get_db()
            article = db.execute("SELECT id FROM articles").fetchone()
            return article["id"]

    def test_mark_read(self, client, article_id):
        response = client.post(f"/articles/{article_id}/read", follow_redirects=True)
        assert response.status_code == 200

    def test_mark_read_ajax(self, client, article_id):
        response = client.post(
            f"/articles/{article_id}/read",
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        assert response.status_code == 200
        assert response.json["success"] is True

    def test_mark_unread(self, client, article_id):
        response = client.post(f"/articles/{article_id}/unread", follow_redirects=True)
        assert response.status_code == 200

    def test_mark_all_read(self, client, article_id):
        response = client.post("/articles/mark-all-read", follow_redirects=True)
        assert response.status_code == 200


class TestApiRoutes:
    def test_api_feeds(self, client, mock_feed_fetch):
        client.post("/feeds/add", data={"url": "https://example.com/feed.xml"})

        response = client.get("/api/feeds")
        assert response.status_code == 200

        data = response.json
        assert len(data) == 1
        assert data[0]["title"] == "Test Feed"

    def test_api_articles(self, client, mock_feed_fetch):
        client.post("/feeds/add", data={"url": "https://example.com/feed.xml"})

        response = client.get("/api/articles")
        assert response.status_code == 200

        data = response.json
        assert len(data) == 1
        assert data[0]["title"] == "Test Article"
