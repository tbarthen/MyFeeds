import html
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from typing import Tuple
from urllib.parse import urlparse

import feedparser
import requests

from src.app.database import get_db
from src.app.models import Feed, Article


FETCH_TIMEOUT = 30
MAX_ERROR_COUNT = 3
USER_AGENT = "MyFeeds/1.0 (RSS Reader; +https://github.com/myfeeds)"
ALLOWED_SCHEMES = {"http", "https"}

UNSUBSCRIBED_FEED_URL = "myfeeds:unsubscribed"
UNSUBSCRIBED_FEED_TITLE = "Unsubscribed"


def get_all_feeds() -> list[Feed]:
    """Feeds shown in the sidebar: active subscriptions, plus the Unsubscribed
    archive only while it actually holds articles."""
    db = get_db()
    rows = db.execute("""
        SELECT f.*,
               COUNT(CASE WHEN a.is_read = 0 THEN 1 END) as unread_count,
               COUNT(a.id) as total_count
        FROM feeds f
        LEFT JOIN articles a ON f.id = a.feed_id
        WHERE f.unsubscribed = 0
        GROUP BY f.id
        HAVING f.url != ? OR total_count > 0
        ORDER BY f.hidden, f.title COLLATE NOCASE
    """, (UNSUBSCRIBED_FEED_URL,)).fetchall()
    return [Feed.from_row(row) for row in rows]


def get_unsubscribed_feeds() -> list[Feed]:
    db = get_db()
    rows = db.execute("""
        SELECT f.*, 0 as unread_count
        FROM feeds f
        WHERE f.unsubscribed = 1
        ORDER BY f.title COLLATE NOCASE
    """).fetchall()
    return [Feed.from_row(row) for row in rows]


def get_or_create_unsubscribed_feed() -> int:
    """Return the id of the persistent 'Unsubscribed' archive feed, creating it
    on first use."""
    db = get_db()
    row = db.execute(
        "SELECT id FROM feeds WHERE url = ?", (UNSUBSCRIBED_FEED_URL,)
    ).fetchone()
    if row:
        return row["id"]
    cursor = db.execute(
        "INSERT INTO feeds (url, title, site_url) VALUES (?, ?, ?)",
        (UNSUBSCRIBED_FEED_URL, UNSUBSCRIBED_FEED_TITLE, "")
    )
    db.commit()
    return cursor.lastrowid


def get_feed_by_id(feed_id: int) -> Feed | None:
    db = get_db()
    row = db.execute("""
        SELECT f.*,
               COUNT(CASE WHEN a.is_read = 0 THEN 1 END) as unread_count
        FROM feeds f
        LEFT JOIN articles a ON f.id = a.feed_id
        WHERE f.id = ?
        GROUP BY f.id
    """, (feed_id,)).fetchone()
    return Feed.from_row(row) if row else None


def add_feed(url: str) -> Tuple[Feed | None, str | None]:
    db = get_db()

    existing = db.execute("SELECT id FROM feeds WHERE url = ?", (url,)).fetchone()
    if existing:
        return None, "Feed already exists"

    result = fetch_and_parse_feed(url)
    if result.error:
        return None, result.error

    title = result.parsed.feed.get("title", url)
    site_url = result.parsed.feed.get("link", "")

    cursor = db.execute(
        "INSERT INTO feeds (url, title, site_url, last_fetched, etag, last_modified) VALUES (?, ?, ?, ?, ?, ?)",
        (url, title, site_url, datetime.now(timezone.utc).isoformat(), result.etag, result.last_modified)
    )
    feed_id = cursor.lastrowid
    db.commit()

    save_articles_from_parsed(feed_id, result.parsed)

    return get_feed_by_id(feed_id), None


def set_feed_hidden(feed_id: int, hidden: bool) -> bool:
    db = get_db()
    cursor = db.execute(
        "UPDATE feeds SET hidden = ? WHERE id = ?",
        (1 if hidden else 0, feed_id)
    )
    db.commit()
    return cursor.rowcount > 0


def toggle_feed_hidden(feed_id: int) -> bool | None:
    db = get_db()
    row = db.execute("SELECT hidden FROM feeds WHERE id = ?", (feed_id,)).fetchone()
    if not row:
        return None

    new_value = 0 if row["hidden"] else 1
    db.execute("UPDATE feeds SET hidden = ? WHERE id = ?", (new_value, feed_id))
    db.commit()
    return bool(new_value)


def unsubscribe_feed(feed_id: int) -> bool:
    """Non-destructive unsubscribe: move the feed's articles to the Unsubscribed
    archive and flag the original so it stops fetching and leaves the sidebar,
    while keeping its config for a later resubscribe."""
    db = get_db()
    feed = db.execute(
        "SELECT id, url, unsubscribed FROM feeds WHERE id = ?", (feed_id,)
    ).fetchone()
    if not feed or feed["unsubscribed"] or feed["url"] == UNSUBSCRIBED_FEED_URL:
        return False

    archive_id = get_or_create_unsubscribed_feed()
    db.execute(
        "UPDATE OR IGNORE articles SET feed_id = ? WHERE feed_id = ?",
        (archive_id, feed_id)
    )
    db.execute("DELETE FROM articles WHERE feed_id = ?", (feed_id,))
    db.execute("UPDATE feeds SET unsubscribed = 1 WHERE id = ?", (feed_id,))
    db.commit()
    return True


def resubscribe_feeds(feed_ids: list[int]) -> int:
    """Restore unsubscribed feeds as active subscriptions and reset their fetch
    state so the next refresh pulls fresh articles. Old articles stay under the
    Unsubscribed archive."""
    if not feed_ids:
        return 0

    db = get_db()
    count = 0
    for feed_id in feed_ids:
        cursor = db.execute("""
            UPDATE feeds
            SET unsubscribed = 0, etag = NULL, last_modified = NULL,
                fetch_error_count = 0, last_error = NULL
            WHERE id = ? AND unsubscribed = 1
        """, (feed_id,))
        count += cursor.rowcount
    db.commit()
    return count


def delete_unsubscribed_feeds(feed_ids: list[int]) -> int:
    """Permanently remove unsubscribed feeds' retained config so they can no
    longer be resubscribed. Their old articles already live under the
    Unsubscribed archive (a different feed_id) and are left untouched."""
    if not feed_ids:
        return 0

    db = get_db()
    count = 0
    for feed_id in feed_ids:
        cursor = db.execute(
            "DELETE FROM feeds WHERE id = ? AND unsubscribed = 1", (feed_id,)
        )
        count += cursor.rowcount
    db.commit()
    return count


def refresh_feed(feed_id: int) -> Tuple[int, str | None]:
    db = get_db()
    feed_row = db.execute(
        "SELECT url, etag, last_modified, unsubscribed FROM feeds WHERE id = ?", (feed_id,)
    ).fetchone()
    if not feed_row:
        return 0, "Feed not found"
    if feed_row["unsubscribed"] or feed_row["url"] == UNSUBSCRIBED_FEED_URL:
        return 0, None

    result = fetch_and_parse_feed(feed_row["url"], etag=feed_row["etag"],
                                   last_modified=feed_row["last_modified"])
    if result.not_modified:
        db.execute("""
            UPDATE feeds SET last_fetched = ?, fetch_error_count = 0, last_error = NULL
            WHERE id = ?
        """, (datetime.now(timezone.utc).isoformat(), feed_id))
        db.commit()
        return 0, "not_modified"

    if result.error:
        error_count = db.execute(
            "SELECT fetch_error_count FROM feeds WHERE id = ?", (feed_id,)
        ).fetchone()["fetch_error_count"]

        db.execute("""
            UPDATE feeds
            SET fetch_error_count = ?, last_error = ?
            WHERE id = ?
        """, (error_count + 1, result.error, feed_id))
        db.commit()
        return 0, result.error

    db.execute("""
        UPDATE feeds
        SET last_fetched = ?, fetch_error_count = 0, last_error = NULL,
            etag = ?, last_modified = ?
        WHERE id = ?
    """, (datetime.now(timezone.utc).isoformat(), result.etag, result.last_modified, feed_id))
    db.commit()

    new_count = save_articles_from_parsed(feed_id, result.parsed, apply_age_gate=True)
    return new_count, None


REFRESH_DELAY_SECONDS = 5


def refresh_all_feeds() -> dict[int, Tuple[int, str | None]]:
    results = {}
    feeds = get_all_feeds()
    for i, feed in enumerate(feeds):
        if feed.url == UNSUBSCRIBED_FEED_URL:
            continue
        if feed.fetch_error_count >= MAX_ERROR_COUNT:
            results[feed.id] = (0, f"skipped: {feed.fetch_error_count} consecutive errors")
            continue
        results[feed.id] = refresh_feed(feed.id)
        if i < len(feeds) - 1:
            time.sleep(REFRESH_DELAY_SECONDS)
    return results


def _is_safe_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ALLOWED_SCHEMES and bool(parsed.hostname)


class FeedFetchResult:
    def __init__(self, parsed: feedparser.FeedParserDict | None, error: str | None,
                 not_modified: bool = False, etag: str | None = None,
                 last_modified: str | None = None):
        self.parsed = parsed
        self.error = error
        self.not_modified = not_modified
        self.etag = etag
        self.last_modified = last_modified


def fetch_and_parse_feed(url: str, etag: str | None = None,
                         last_modified: str | None = None) -> FeedFetchResult:
    if not _is_safe_url(url):
        return FeedFetchResult(None, "only http and https URLs are allowed")

    try:
        headers = {"User-Agent": USER_AGENT}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        response = requests.get(url, timeout=FETCH_TIMEOUT, headers=headers)
        if response.status_code == 304:
            return FeedFetchResult(None, None, not_modified=True)
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        return FeedFetchResult(None, "couldn't reach that site (check the URL)")
    except requests.exceptions.Timeout:
        return FeedFetchResult(None, "that site took too long to respond")
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "unknown"
        if status == 404:
            return FeedFetchResult(None, "nothing found at that URL (404)")
        elif status == 403:
            return FeedFetchResult(None, "that site blocked the request (403)")
        elif status == 401:
            return FeedFetchResult(None, "that feed requires a login (401)")
        else:
            return FeedFetchResult(None, f"that site returned an error ({status})")
    except requests.RequestException as e:
        return FeedFetchResult(None, f"couldn't fetch: {str(e)}")

    parsed = feedparser.parse(response.content)
    if parsed.bozo and not parsed.entries:
        return FeedFetchResult(None, "that URL doesn't contain a valid RSS/Atom feed")

    MAX_HEADER_LEN = 256
    etag_val = response.headers.get("ETag")
    last_mod_val = response.headers.get("Last-Modified")

    return FeedFetchResult(
        parsed, None,
        etag=etag_val[:MAX_HEADER_LEN] if etag_val else None,
        last_modified=last_mod_val[:MAX_HEADER_LEN] if last_mod_val else None,
    )


def extract_image_url(entry) -> str | None:
    """Extract the best image URL from an RSS entry."""
    # Try media:thumbnail first (commonly used)
    if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        return entry.media_thumbnail[0].get("url")

    # Try media:content with image type
    if hasattr(entry, "media_content") and entry.media_content:
        for media in entry.media_content:
            media_type = media.get("type", "")
            if media_type.startswith("image/") or media.get("medium") == "image":
                return media.get("url")

    # Try enclosures
    if hasattr(entry, "enclosures") and entry.enclosures:
        for enclosure in entry.enclosures:
            enc_type = enclosure.get("type", "")
            if enc_type.startswith("image/"):
                return enclosure.get("href") or enclosure.get("url")

    # Try to find image in content/summary HTML
    content_html = ""
    if entry.get("content"):
        content_html = entry.content[0].get("value", "")
    if not content_html:
        content_html = entry.get("summary", "")

    if content_html:
        img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content_html)
        if img_match:
            return img_match.group(1)

    return None


def _parse_entry_datetime(entry) -> datetime | None:
    """Return an entry's published (or updated) time, or None if it has neither."""
    if entry.get("published_parsed"):
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    if entry.get("updated_parsed"):
        return datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
    return None


def _guid_is_seen(db: sqlite3.Connection, feed_id: int, guid: str) -> bool:
    return db.execute(
        "SELECT 1 FROM seen_guids WHERE feed_id = ? AND guid = ?", (feed_id, guid)
    ).fetchone() is not None


def _record_seen_guid(db: sqlite3.Connection, feed_id: int, guid: str) -> None:
    db.execute(
        "INSERT OR IGNORE INTO seen_guids (feed_id, guid) VALUES (?, ?)", (feed_id, guid)
    )


def save_articles_from_parsed(feed_id: int, parsed: feedparser.FeedParserDict,
                              apply_age_gate: bool = False) -> int:
    from src.app.services import article_service, filter_service

    db = get_db()
    new_count = 0
    compiled_filters = filter_service.get_compiled_active_filters()
    cutoff = datetime.now(timezone.utc) - timedelta(days=article_service.RETENTION_DAYS)

    new_articles = []

    for entry in parsed.entries:
        guid = entry.get("id") or entry.get("link") or entry.get("title", "")
        if not guid:
            continue

        published_dt = _parse_entry_datetime(entry)
        undated = published_dt is None

        if apply_age_gate:
            if not undated and published_dt < cutoff:
                continue
            if undated and _guid_is_seen(db, feed_id, guid):
                continue

        title = html.unescape(entry.get("title", ""))
        summary = html.unescape(entry.get("summary", ""))
        content = ""
        if entry.get("content"):
            content = entry.content[0].get("value", "")
        url = entry.get("link", "")
        image_url = extract_image_url(entry)

        published_at = published_dt.isoformat() if published_dt else None

        try:
            cursor = db.execute("""
                INSERT INTO articles (feed_id, guid, title, summary, content, url, image_url, published_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (feed_id, guid, title, summary, content, url, image_url, published_at))
            new_articles.append((cursor.lastrowid, title, summary))
            new_count += 1
            if undated:
                _record_seen_guid(db, feed_id, guid)
        except sqlite3.IntegrityError:
            pass

    if new_articles:
        db.commit()
        filter_service.apply_filters_to_articles(new_articles, compiled_filters=compiled_filters)

    return new_count
