"""Read YouTube channel and playlist feeds through the YouTube Data API.

YouTube's public RSS endpoint (/feeds/videos.xml) is unreliable, so feeds
pointing at it are served from the API instead. Authentication uses the
access token the Google Cloud VM hands out for its own service account, so
there is no API key to store or rotate. Off Google Cloud no token is
available and callers fall back to plain RSS.
"""
import time
from urllib.parse import parse_qs, urlparse

import feedparser
import requests


YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com"}
YOUTUBE_FEED_PATH = "/feeds/videos.xml"
CHANNEL_ID_PREFIX = "UC"
UPLOADS_PLAYLIST_PREFIX = "UU"

METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1/"
    "instance/service-accounts/default/token"
)
METADATA_HEADERS = {"Metadata-Flavor": "Google"}
METADATA_TIMEOUT = 2

PLAYLIST_ITEMS_URL = "https://youtube.googleapis.com/youtube/v3/playlistItems"
PLAYLIST_PAGE_SIZE = 50
API_TIMEOUT = 20
PUBLISHED_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
THUMBNAIL_PREFERENCE = ("high", "medium", "default")

VIDEO_GUID_PREFIX = "yt:video:"
VIDEO_URL = "https://www.youtube.com/watch?v={video_id}"
CHANNEL_URL = "https://www.youtube.com/channel/{channel_id}"


def playlist_id_for_feed_url(url: str) -> str | None:
    """Return the playlist behind a YouTube RSS feed URL, or None for any other URL.

    A channel feed maps to that channel's uploads playlist.
    """
    parsed = urlparse(url or "")
    if parsed.hostname not in YOUTUBE_HOSTS or parsed.path != YOUTUBE_FEED_PATH:
        return None

    query = parse_qs(parsed.query)
    playlist_id = (query.get("playlist_id") or [""])[0]
    if playlist_id:
        return playlist_id

    channel_id = (query.get("channel_id") or [""])[0]
    if channel_id.startswith(CHANNEL_ID_PREFIX):
        return UPLOADS_PLAYLIST_PREFIX + channel_id[len(CHANNEL_ID_PREFIX):]
    return None


def get_access_token() -> str | None:
    """Return the VM service account's access token, or None when not on Google Cloud."""
    try:
        response = requests.get(
            METADATA_TOKEN_URL, headers=METADATA_HEADERS, timeout=METADATA_TIMEOUT
        )
        response.raise_for_status()
        return response.json().get("access_token") or None
    except (requests.RequestException, ValueError):
        return None


def fetch_playlist(playlist_id: str, access_token: str) -> feedparser.FeedParserDict:
    """Fetch a playlist's newest videos, shaped like a parsed RSS feed.

    Raises requests.RequestException when the API call fails.
    """
    response = requests.get(
        PLAYLIST_ITEMS_URL,
        params={"part": "snippet", "playlistId": playlist_id, "maxResults": PLAYLIST_PAGE_SIZE},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=API_TIMEOUT,
    )
    response.raise_for_status()
    snippets = [item.get("snippet") or {} for item in response.json().get("items", [])]

    entries = [_entry_from_snippet(snippet) for snippet in snippets]
    return feedparser.FeedParserDict(
        feed=_feed_meta(snippets),
        entries=[entry for entry in entries if entry is not None],
        bozo=False,
    )


def _feed_meta(snippets: list[dict]) -> feedparser.FeedParserDict:
    first = snippets[0] if snippets else {}
    channel_id = first.get("channelId", "")
    return feedparser.FeedParserDict(
        title=first.get("channelTitle", ""),
        link=CHANNEL_URL.format(channel_id=channel_id) if channel_id else "",
    )


def _entry_from_snippet(snippet: dict) -> feedparser.FeedParserDict | None:
    video_id = (snippet.get("resourceId") or {}).get("videoId")
    if not video_id:
        return None

    entry = feedparser.FeedParserDict(
        id=VIDEO_GUID_PREFIX + video_id,
        title=snippet.get("title", ""),
        summary=snippet.get("description", ""),
        link=VIDEO_URL.format(video_id=video_id),
    )
    published = _parse_published(snippet.get("publishedAt"))
    if published is not None:
        entry["published_parsed"] = published
    thumbnail_url = _best_thumbnail_url(snippet.get("thumbnails") or {})
    if thumbnail_url:
        entry["media_thumbnail"] = [{"url": thumbnail_url}]
    return entry


def _parse_published(published_at: str | None) -> time.struct_time | None:
    try:
        return time.strptime(published_at or "", PUBLISHED_FORMAT)
    except ValueError:
        return None


def _best_thumbnail_url(thumbnails: dict) -> str | None:
    for size in THUMBNAIL_PREFERENCE:
        url = (thumbnails.get(size) or {}).get("url")
        if url:
            return url
    return None
