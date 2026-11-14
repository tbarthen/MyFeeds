"""Long-term preservation of saved articles.

Saved articles get their full text extracted from the original page and a
Wayback Machine snapshot requested, so they stay readable after the source
page changes or disappears. Runs from the scheduler container only.
"""
import html
import logging
import re
from urllib.parse import quote

import requests
import trafilatura

from src.app.database import get_db

logger = logging.getLogger(__name__)

MAX_EXTRACT_ATTEMPTS = 3
BATCH_SIZE = 5
PAGE_FETCH_TIMEOUT = 20
WAYBACK_SAVE_TIMEOUT = 30
MIN_TEXT_LENGTH = 200

PAGE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
ARCHIVE_TODAY_NEWEST = "https://archive.ph/newest/"
WAYBACK_LATEST = "https://web.archive.org/web/"
WAYBACK_SAVE = "https://web.archive.org/save/"
URL_SAFE_CHARS = ":/?&=#%+@,;~"

BLOCK_TAG_PATTERN = re.compile(r"<\s*(br|/p|/div|/li|/h[1-6]|/blockquote)\b[^>]*>", re.IGNORECASE)
ANY_TAG_PATTERN = re.compile(r"<[^>]+>")


def archive_today_url(url: str) -> str:
    """Link to archive.today's most recent snapshot of url."""
    return ARCHIVE_TODAY_NEWEST + quote(url, safe=URL_SAFE_CHARS)


def wayback_url(url: str) -> str:
    """Link to the Wayback Machine's most recent snapshot of url."""
    return WAYBACK_LATEST + quote(url, safe=URL_SAFE_CHARS)


def to_paragraphs(text: str | None) -> list[str]:
    """Split plain text into non-empty, trimmed paragraphs."""
    if not text:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def html_to_text(markup: str | None) -> str:
    """Convert feed HTML to plain text, keeping paragraph breaks."""
    if not markup:
        return ""
    with_breaks = BLOCK_TAG_PATTERN.sub("\n", markup)
    return html.unescape(ANY_TAG_PATTERN.sub("", with_breaks))


def fetch_page(url: str) -> str | None:
    """Download a page's HTML, or None on any network or HTTP error."""
    try:
        response = requests.get(
            url,
            timeout=PAGE_FETCH_TIMEOUT,
            headers={"User-Agent": PAGE_USER_AGENT},
        )
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logger.warning("Page fetch failed for %s: %s", url, e)
        return None


def extract_text(page_html: str | None, url: str) -> str | None:
    """Pull the main article text out of a page, or None if too little is found."""
    if not page_html:
        return None
    text = trafilatura.extract(page_html, url=url, include_comments=False, include_tables=False)
    if not text or len(text) < MIN_TEXT_LENGTH:
        return None
    return text


def request_wayback_save(url: str) -> bool:
    """Ask the Wayback Machine to snapshot url. A timeout still counts as requested."""
    try:
        response = requests.get(
            WAYBACK_SAVE + quote(url, safe=URL_SAFE_CHARS),
            timeout=WAYBACK_SAVE_TIMEOUT,
            headers={"User-Agent": PAGE_USER_AGENT},
        )
        return response.ok
    except requests.Timeout:
        return True
    except requests.RequestException as e:
        logger.warning("Wayback save failed for %s: %s", url, e)
        return False


def get_pending_articles(limit: int = BATCH_SIZE) -> list:
    """Saved articles that still need text extraction or a Wayback snapshot."""
    return get_db().execute(
        "SELECT id, url, full_text, extract_attempts, wayback_saved_at FROM articles "
        "WHERE is_saved = 1 AND url IS NOT NULL AND url != '' AND ("
        "  (full_text IS NULL AND extract_attempts < ?) OR wayback_saved_at IS NULL"
        ") ORDER BY id LIMIT ?",
        (MAX_EXTRACT_ATTEMPTS, limit),
    ).fetchall()


def _needs_extraction(row) -> bool:
    return row["full_text"] is None and row["extract_attempts"] < MAX_EXTRACT_ATTEMPTS


def _store_extraction(article_id: int, text: str | None) -> None:
    get_db().execute(
        "UPDATE articles SET full_text = ?, extract_attempts = extract_attempts + 1 WHERE id = ?",
        (text, article_id),
    )


def _mark_wayback_requested(article_id: int) -> None:
    get_db().execute(
        "UPDATE articles SET wayback_saved_at = CURRENT_TIMESTAMP WHERE id = ?",
        (article_id,),
    )


def process_article(row) -> None:
    """Extract text and request a Wayback snapshot for one pending article."""
    url = row["url"]
    if _needs_extraction(row):
        _store_extraction(row["id"], extract_text(fetch_page(url), url))
    if row["wayback_saved_at"] is None:
        request_wayback_save(url)
        _mark_wayback_requested(row["id"])
    get_db().commit()


def process_pending(limit: int = BATCH_SIZE) -> int:
    """Process a batch of pending saved articles. Returns how many were handled."""
    rows = get_pending_articles(limit)
    for row in rows:
        process_article(row)
    return len(rows)


def extraction_state(full_text: str | None, attempts: int) -> str:
    """'done', 'pending', or 'failed' for a saved article's text extraction."""
    if full_text:
        return "done"
    if attempts < MAX_EXTRACT_ATTEMPTS:
        return "pending"
    return "failed"
