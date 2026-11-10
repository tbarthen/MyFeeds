from unittest.mock import MagicMock, patch

import pytest
import requests

from src.app.services import article_service, feed_service, youtube_service


CHANNEL_FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id=UCabc123"
PLAYLIST_FEED_URL = "https://www.youtube.com/feeds/videos.xml?playlist_id=PLxyz"
RECENT_PUBLISHED = "2099-01-02T03:04:05Z"


def make_item(video_id="vid1", title="Scoreboard - GM", description="Rated 7.3/10",
              published=RECENT_PUBLISHED):
    return {"snippet": {
        "title": title,
        "description": description,
        "publishedAt": published,
        "channelId": "UCabc123",
        "channelTitle": "The Channel",
        "resourceId": {"videoId": video_id},
        "thumbnails": {
            "default": {"url": "https://img/default.jpg"},
            "high": {"url": "https://img/high.jpg"},
        },
    }}


def api_response(items, status_code=200):
    response = MagicMock(status_code=status_code)
    response.json.return_value = {"items": items}
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=response)
    return response


@pytest.fixture
def youtube_api():
    """Patch the token lookup and the API call; yields the API mock."""
    with patch.object(youtube_service, "get_access_token", return_value="token"), \
            patch("src.app.services.youtube_service.requests.get") as mock_get:
        mock_get.return_value = api_response([make_item()])
        yield mock_get


class TestPlaylistIdForFeedUrl:
    def test_channel_feed_maps_to_uploads_playlist(self):
        assert youtube_service.playlist_id_for_feed_url(CHANNEL_FEED_URL) == "UUabc123"

    def test_playlist_feed_keeps_its_playlist(self):
        assert youtube_service.playlist_id_for_feed_url(PLAYLIST_FEED_URL) == "PLxyz"

    @pytest.mark.parametrize("url", [
        "https://example.com/feed.xml",
        "https://www.youtube.com/watch?v=abc",
        "https://www.youtube.com/feeds/videos.xml?user=someone",
        "https://evil.example/feeds/videos.xml?channel_id=UCabc123",
        "",
    ])
    def test_other_urls_are_not_youtube_feeds(self, url):
        assert youtube_service.playlist_id_for_feed_url(url) is None


class TestGetAccessToken:
    def test_returns_token_from_metadata_server(self):
        with patch("src.app.services.youtube_service.requests.get") as mock_get:
            mock_get.return_value.json.return_value = {"access_token": "abc"}
            assert youtube_service.get_access_token() == "abc"

    def test_returns_none_off_google_cloud(self):
        with patch("src.app.services.youtube_service.requests.get",
                   side_effect=requests.exceptions.ConnectionError()):
            assert youtube_service.get_access_token() is None


class TestFetchPlaylist:
    def test_shapes_videos_like_feed_entries(self, youtube_api):
        parsed = youtube_service.fetch_playlist("UUabc123", "token")

        assert parsed.feed.title == "The Channel"
        assert parsed.feed.link == "https://www.youtube.com/channel/UCabc123"
        entry = parsed.entries[0]
        assert entry.id == "yt:video:vid1"
        assert entry.link == "https://www.youtube.com/watch?v=vid1"
        assert entry.summary == "Rated 7.3/10"
        assert tuple(entry.published_parsed[:6]) == (2099, 1, 2, 3, 4, 5)
        assert entry.media_thumbnail[0]["url"] == "https://img/high.jpg"

    def test_skips_items_without_a_video_id(self, youtube_api):
        youtube_api.return_value = api_response([{"snippet": {"title": "Deleted video"}}])

        assert youtube_service.fetch_playlist("UUabc123", "token").entries == []


class TestYoutubeFeedFetching:
    def test_add_feed_reads_videos_from_api(self, app, youtube_api):
        with app.app_context():
            feed, error = feed_service.add_feed(CHANNEL_FEED_URL)

            assert error is None
            assert feed.title == "The Channel"
            articles = article_service.get_articles(feed_id=feed.id)
            assert [a.title for a in articles] == ["Scoreboard - GM"]
            assert articles[0].image_url == "https://img/high.jpg"
            assert youtube_api.call_args.kwargs["params"]["playlistId"] == "UUabc123"

    def test_refresh_adds_new_videos_and_clears_error_state(self, app, youtube_api):
        with app.app_context():
            feed, _ = feed_service.add_feed(CHANNEL_FEED_URL)
            youtube_api.return_value = api_response(
                [make_item("vid2", "New video"), make_item()]
            )

            new_count, error = feed_service.refresh_feed(feed.id)

            assert error is None
            assert new_count == 1

    def test_api_error_is_reported_as_feed_error(self, youtube_api):
        youtube_api.return_value = api_response([], status_code=403)

        result = feed_service.fetch_and_parse_feed(CHANNEL_FEED_URL)

        assert result.error == "YouTube returned an error (403)"

    def test_falls_back_to_rss_without_google_credentials(self):
        with patch.object(youtube_service, "get_access_token", return_value=None), \
                patch("src.app.services.feed_service.requests.get") as rss_get:
            rss_get.return_value = MagicMock(status_code=404)
            rss_get.return_value.raise_for_status.side_effect = (
                requests.exceptions.HTTPError(response=rss_get.return_value)
            )

            result = feed_service.fetch_and_parse_feed(CHANNEL_FEED_URL)

            assert rss_get.called
            assert result.error == "nothing found at that URL (404)"

    def test_non_youtube_feed_never_asks_for_a_token(self):
        with patch.object(youtube_service, "get_access_token") as get_token, \
                patch("src.app.services.feed_service.requests.get") as rss_get:
            rss_get.return_value = MagicMock(content=b"", status_code=200, headers={})

            feed_service.fetch_and_parse_feed("https://example.com/feed.xml")

            get_token.assert_not_called()
