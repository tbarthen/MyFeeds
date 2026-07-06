from datetime import datetime, timedelta, timezone
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
        mock_response = MagicMock(content=b"<xml></xml>", status_code=200)
        mock_response.headers = {}
        mock.return_value = mock_response
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


class TestFeedVisibility:
    def test_new_feed_is_visible_by_default(self, app, mock_requests_get, mock_feedparser):
        with app.app_context():
            feed, _ = feed_service.add_feed("https://example.com/feed.xml")
            assert feed.hidden is False

    def test_set_and_toggle_hidden(self, app, mock_requests_get, mock_feedparser):
        with app.app_context():
            feed, _ = feed_service.add_feed("https://example.com/feed.xml")

            assert feed_service.set_feed_hidden(feed.id, True) is True
            assert feed_service.get_feed_by_id(feed.id).hidden is True

            assert feed_service.toggle_feed_hidden(feed.id) is False
            assert feed_service.get_feed_by_id(feed.id).hidden is False

            assert feed_service.toggle_feed_hidden(feed.id) is True
            assert feed_service.get_feed_by_id(feed.id).hidden is True

    def test_toggle_hidden_missing_feed_returns_none(self, app):
        with app.app_context():
            assert feed_service.toggle_feed_hidden(999) is None

    def test_hidden_feed_excluded_from_aggregate_views(self, app, mock_requests_get, mock_feedparser):
        with app.app_context():
            from src.app.services import article_service

            feed, _ = feed_service.add_feed("https://example.com/feed.xml")
            assert article_service.get_unread_count() == 1
            assert len(article_service.get_articles()) == 1

            feed_service.set_feed_hidden(feed.id, True)

            assert article_service.get_unread_count() == 0
            assert article_service.get_articles() == []
            assert len(article_service.get_articles(feed_id=feed.id)) == 1

    def test_hidden_feed_saved_articles_still_visible(self, app, mock_requests_get, mock_feedparser):
        with app.app_context():
            from src.app.services import article_service

            feed, _ = feed_service.add_feed("https://example.com/feed.xml")
            article = article_service.get_articles(feed_id=feed.id)[0]
            article_service.toggle_saved(article.id)

            feed_service.set_feed_hidden(feed.id, True)

            assert len(article_service.get_articles(saved_only=True)) == 1

    def test_hidden_feeds_sorted_last(self, app, mock_requests_get, mock_feedparser):
        with app.app_context():
            visible, _ = feed_service.add_feed("https://a.com/feed.xml")
            hidden, _ = feed_service.add_feed("https://b.com/feed.xml")
            feed_service.set_feed_hidden(hidden.id, True)

            feeds = feed_service.get_all_feeds()
            assert feeds[0].id == visible.id
            assert feeds[-1].id == hidden.id


class TestUnsubscribe:
    def _count(self, feed_id):
        from src.app.database import get_db
        return get_db().execute(
            "SELECT COUNT(*) FROM articles WHERE feed_id = ?", (feed_id,)
        ).fetchone()[0]

    def _archive_id(self):
        from src.app.database import get_db
        row = get_db().execute(
            "SELECT id FROM feeds WHERE url = ?", (feed_service.UNSUBSCRIBED_FEED_URL,)
        ).fetchone()
        return row["id"] if row else None

    def test_unsubscribe_moves_articles_to_archive(self, app, mock_requests_get, mock_feedparser):
        with app.app_context():
            from src.app.database import get_db
            feed, _ = feed_service.add_feed("https://example.com/feed.xml")

            assert feed_service.unsubscribe_feed(feed.id) is True

            row = get_db().execute(
                "SELECT unsubscribed FROM feeds WHERE id = ?", (feed.id,)
            ).fetchone()
            assert row["unsubscribed"] == 1
            assert self._count(feed.id) == 0
            assert self._count(self._archive_id()) == 1

    def test_unsubscribed_feed_leaves_sidebar_archive_appears(self, app, mock_requests_get, mock_feedparser):
        with app.app_context():
            feed, _ = feed_service.add_feed("https://example.com/feed.xml")
            feed_service.unsubscribe_feed(feed.id)

            titles = [f.title for f in feed_service.get_all_feeds()]
            assert "Test Feed" not in titles
            assert feed_service.UNSUBSCRIBED_FEED_TITLE in titles

    def test_archive_hidden_while_empty(self, app):
        with app.app_context():
            feed_service.get_or_create_unsubscribed_feed()
            titles = [f.title for f in feed_service.get_all_feeds()]
            assert feed_service.UNSUBSCRIBED_FEED_TITLE not in titles

    def test_unsubscribed_feed_listed_in_picker(self, app, mock_requests_get, mock_feedparser):
        with app.app_context():
            feed, _ = feed_service.add_feed("https://example.com/feed.xml")
            feed_service.unsubscribe_feed(feed.id)
            assert [f.id for f in feed_service.get_unsubscribed_feeds()] == [feed.id]

    def test_resubscribe_restores_feed_and_keeps_old_articles_archived(self, app, mock_requests_get, mock_feedparser):
        with app.app_context():
            feed, _ = feed_service.add_feed("https://example.com/feed.xml")
            feed_service.unsubscribe_feed(feed.id)

            assert feed_service.resubscribe_feeds([feed.id]) == 1
            assert "Test Feed" in [f.title for f in feed_service.get_all_feeds()]
            assert feed_service.get_unsubscribed_feeds() == []
            assert self._count(feed.id) == 0
            assert self._count(self._archive_id()) == 1

    def test_cannot_unsubscribe_the_archive(self, app):
        with app.app_context():
            archive_id = feed_service.get_or_create_unsubscribed_feed()
            assert feed_service.unsubscribe_feed(archive_id) is False

    def test_duplicate_guid_merge_is_safe(self, app, mock_requests_get, mock_feedparser):
        with app.app_context():
            a, _ = feed_service.add_feed("https://a.com/feed.xml")
            b, _ = feed_service.add_feed("https://b.com/feed.xml")

            assert feed_service.unsubscribe_feed(a.id) is True
            assert feed_service.unsubscribe_feed(b.id) is True

            assert self._count(self._archive_id()) == 1
            assert self._count(b.id) == 0

    def test_refresh_all_skips_archive(self, app, mock_requests_get, mock_feedparser):
        with app.app_context():
            feed, _ = feed_service.add_feed("https://example.com/feed.xml")
            feed_service.unsubscribe_feed(feed.id)
            results = feed_service.refresh_all_feeds()
            assert self._archive_id() not in results

    def test_delete_unsubscribed_removes_config_but_keeps_archive(self, app, mock_requests_get, mock_feedparser):
        with app.app_context():
            from src.app.database import get_db
            feed, _ = feed_service.add_feed("https://example.com/feed.xml")
            feed_service.unsubscribe_feed(feed.id)
            archive_id = self._archive_id()
            assert self._count(archive_id) == 1

            assert feed_service.delete_unsubscribed_feeds([feed.id]) == 1
            assert get_db().execute(
                "SELECT COUNT(*) FROM feeds WHERE id = ?", (feed.id,)
            ).fetchone()[0] == 0
            assert self._count(archive_id) == 1
            assert feed_service.get_unsubscribed_feeds() == []

    def test_delete_unsubscribed_ignores_active_feeds(self, app, mock_requests_get, mock_feedparser):
        with app.app_context():
            from src.app.database import get_db
            feed, _ = feed_service.add_feed("https://example.com/feed.xml")

            assert feed_service.delete_unsubscribed_feeds([feed.id]) == 0
            assert get_db().execute(
                "SELECT COUNT(*) FROM feeds WHERE id = ?", (feed.id,)
            ).fetchone()[0] == 1


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


class TestRefreshFeedAgeGate:
    def test_refresh_skips_entries_older_than_retention(self, app, mock_requests_get, mock_feedparser):
        with app.app_context():
            from src.app.services import article_service

            added_feed, _ = feed_service.add_feed("https://example.com/feed.xml")

            old = (datetime.now(timezone.utc) - timedelta(days=30)).timetuple()
            recent = (datetime.now(timezone.utc) - timedelta(days=1)).timetuple()
            mock_feedparser.return_value = make_mock_parsed_feed(entries=[
                {"id": "old", "title": "Old", "link": "https://example.com/old",
                 "published_parsed": old},
                {"id": "recent", "title": "Recent", "link": "https://example.com/recent",
                 "published_parsed": recent},
            ])

            new_count, error = feed_service.refresh_feed(added_feed.id)

            assert error is None
            assert new_count == 1
            titles = [a.title for a in article_service.get_articles(feed_id=added_feed.id)]
            assert "Recent" in titles
            assert "Old" not in titles

    def test_refresh_keeps_undated_entries(self, app, mock_requests_get, mock_feedparser):
        with app.app_context():
            from src.app.services import article_service

            added_feed, _ = feed_service.add_feed("https://example.com/feed.xml")

            mock_feedparser.return_value = make_mock_parsed_feed(entries=[
                {"id": "undated", "title": "Undated", "link": "https://example.com/undated"},
            ])

            new_count, error = feed_service.refresh_feed(added_feed.id)

            assert error is None
            assert new_count == 1
            titles = [a.title for a in article_service.get_articles(feed_id=added_feed.id)]
            assert "Undated" in titles

    def test_tombstone_prevents_undated_resurrection_after_purge(
        self, app, mock_requests_get, mock_feedparser
    ):
        with app.app_context():
            from src.app.database import get_db
            from src.app.services import article_service

            added_feed, _ = feed_service.add_feed("https://example.com/feed.xml")

            undated_feed = make_mock_parsed_feed(entries=[
                {"id": "undated", "title": "Undated", "link": "https://example.com/undated"},
            ])
            mock_feedparser.return_value = undated_feed

            first_count, _ = feed_service.refresh_feed(added_feed.id)
            assert first_count == 1

            get_db().execute("DELETE FROM articles WHERE guid = 'undated'")
            get_db().commit()

            second_count, error = feed_service.refresh_feed(added_feed.id)

            assert error is None
            assert second_count == 0
            titles = [a.title for a in article_service.get_articles(feed_id=added_feed.id)]
            assert "Undated" not in titles
