from unittest.mock import patch, MagicMock

import pytest
import requests

from src.app.database import get_db
from src.app.services import archive_service

ARTICLE_URL = "https://example.com/news/story?id=7"
LONG_TEXT = "First paragraph of the story.\n" + ("Body sentence. " * 30)
PAGE_HTML = "<html><body><article><p>Real page</p></article></body></html>"


@pytest.fixture
def feed_id(app):
    with app.app_context():
        db = get_db()
        cursor = db.execute(
            "INSERT INTO feeds (url, title) VALUES (?, ?)",
            ("https://example.com/feed.xml", "Test Feed")
        )
        db.commit()
        return cursor.lastrowid


def insert_article(app, feed_id, guid="g1", url=ARTICLE_URL, is_saved=True, **columns):
    with app.app_context():
        db = get_db()
        fields = {"feed_id": feed_id, "guid": guid, "title": "Story", "url": url,
                  "is_saved": int(is_saved), **columns}
        names = ", ".join(fields)
        placeholders = ", ".join("?" for _ in fields)
        cursor = db.execute(
            f"INSERT INTO articles ({names}) VALUES ({placeholders})",
            list(fields.values())
        )
        db.commit()
        return cursor.lastrowid


def fetch_row(app, article_id):
    with app.app_context():
        return dict(get_db().execute(
            "SELECT full_text, extract_attempts, wayback_saved_at FROM articles WHERE id = ?",
            (article_id,)
        ).fetchone())


@pytest.fixture
def network():
    with patch.object(archive_service, "fetch_page", return_value=PAGE_HTML) as fetch, \
         patch.object(archive_service, "extract_text", return_value=LONG_TEXT) as extract, \
         patch.object(archive_service, "request_wayback_save", return_value=True) as wayback:
        yield fetch, extract, wayback


class TestArchiveLinks:
    def test_archive_today_url(self):
        assert archive_service.archive_today_url(ARTICLE_URL) == \
            "https://archive.ph/newest/https://example.com/news/story?id=7"

    def test_wayback_url(self):
        assert archive_service.wayback_url(ARTICLE_URL) == \
            "https://web.archive.org/web/https://example.com/news/story?id=7"

    def test_spaces_are_encoded(self):
        assert " " not in archive_service.wayback_url("https://example.com/a b")


class TestTextHelpers:
    def test_to_paragraphs_drops_blank_lines(self):
        assert archive_service.to_paragraphs("One\n\n  Two  \n") == ["One", "Two"]

    def test_to_paragraphs_handles_none(self):
        assert archive_service.to_paragraphs(None) == []

    def test_html_to_text_keeps_paragraph_breaks(self):
        text = archive_service.html_to_text("<p>One &amp; two</p><p>Three<br>Four</p>")
        assert archive_service.to_paragraphs(text) == ["One & two", "Three", "Four"]

    def test_html_to_text_handles_none(self):
        assert archive_service.html_to_text(None) == ""

    @pytest.mark.parametrize("text, attempts, is_saved, expected", [
        ("body", 0, False, "done"),
        (None, 1, True, "pending"),
        (None, 1, False, "failed"),
        (None, archive_service.MAX_EXTRACT_ATTEMPTS, True, "failed"),
    ])
    def test_extraction_state(self, text, attempts, is_saved, expected):
        assert archive_service.extraction_state(text, attempts, is_saved) == expected


class TestExtractText:
    def test_returns_none_for_empty_page(self):
        assert archive_service.extract_text(None, ARTICLE_URL) is None

    def test_rejects_short_extracts(self):
        with patch.object(archive_service.trafilatura, "extract", return_value="Too short"):
            assert archive_service.extract_text(PAGE_HTML, ARTICLE_URL) is None

    def test_returns_long_extracts(self):
        with patch.object(archive_service.trafilatura, "extract", return_value=LONG_TEXT):
            assert archive_service.extract_text(PAGE_HTML, ARTICLE_URL) == LONG_TEXT

    def test_real_extraction(self):
        paragraphs = "".join(f"<p>{'Sentence number %d of the story. ' % i * 8}</p>" for i in range(6))
        page = f"<html><body><nav>Menu</nav><article><h1>T</h1>{paragraphs}</article></body></html>"
        text = archive_service.extract_text(page, ARTICLE_URL)
        assert text and "Sentence number 3" in text


class TestNetworkCalls:
    def test_fetch_page_returns_none_on_error(self):
        with patch.object(archive_service.requests, "get", side_effect=requests.ConnectionError()):
            assert archive_service.fetch_page(ARTICLE_URL) is None

    def test_fetch_page_returns_none_on_http_error(self):
        response = MagicMock()
        response.raise_for_status.side_effect = requests.HTTPError("403")
        with patch.object(archive_service.requests, "get", return_value=response):
            assert archive_service.fetch_page(ARTICLE_URL) is None

    def test_wayback_timeout_counts_as_requested(self):
        with patch.object(archive_service.requests, "get", side_effect=requests.Timeout()):
            assert archive_service.request_wayback_save(ARTICLE_URL) is True

    def test_wayback_connection_error_is_failure(self):
        with patch.object(archive_service.requests, "get", side_effect=requests.ConnectionError()):
            assert archive_service.request_wayback_save(ARTICLE_URL) is False


class TestProcessPending:
    def test_extracts_text_and_requests_wayback(self, app, feed_id, network):
        article_id = insert_article(app, feed_id)
        with app.app_context():
            assert archive_service.process_pending() == 1

        row = fetch_row(app, article_id)
        assert row["full_text"] == LONG_TEXT
        assert row["extract_attempts"] == 1
        assert row["wayback_saved_at"] is not None
        network[2].assert_called_once_with(ARTICLE_URL)

    def test_done_articles_are_not_reprocessed(self, app, feed_id, network):
        insert_article(app, feed_id)
        with app.app_context():
            archive_service.process_pending()
            assert archive_service.process_pending() == 0

    def test_ignores_unsaved_and_urlless_articles(self, app, feed_id, network):
        insert_article(app, feed_id, guid="unsaved", is_saved=False)
        insert_article(app, feed_id, guid="nourl", url=None)
        with app.app_context():
            assert archive_service.process_pending() == 0

    def test_failed_extraction_retries_then_stops(self, app, feed_id, network):
        network[1].return_value = None
        article_id = insert_article(app, feed_id)
        with app.app_context():
            for _ in range(archive_service.MAX_EXTRACT_ATTEMPTS + 2):
                archive_service.process_pending()

        row = fetch_row(app, article_id)
        assert row["full_text"] is None
        assert row["extract_attempts"] == archive_service.MAX_EXTRACT_ATTEMPTS
        assert network[0].call_count == archive_service.MAX_EXTRACT_ATTEMPTS
        assert network[2].call_count == 1

    def test_wayback_only_when_text_already_present(self, app, feed_id, network):
        insert_article(app, feed_id, full_text=LONG_TEXT)
        with app.app_context():
            assert archive_service.process_pending() == 1
        network[0].assert_not_called()
        network[2].assert_called_once()

    def test_respects_batch_limit(self, app, feed_id, network):
        for i in range(3):
            insert_article(app, feed_id, guid=f"g{i}")
        with app.app_context():
            assert archive_service.process_pending(limit=2) == 2


class TestReaderRoute:
    def test_shows_full_text_and_archive_links(self, app, client, feed_id):
        article_id = insert_article(app, feed_id, full_text="Para one\nPara two",
                                    summary="<p>Feed summary</p>")
        response = client.get(f"/articles/{article_id}/reader")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "<p>Para one</p>" in body and "<p>Para two</p>" in body
        assert "Feed summary" not in body
        assert "https://archive.ph/newest/https://example.com/news/story?id=7" in body
        assert "https://web.archive.org/web/https://example.com/news/story?id=7" in body
        assert "still being fetched" not in body

    def test_extracts_on_demand_for_unsaved_article(self, app, client, feed_id, network):
        article_id = insert_article(app, feed_id, is_saved=False, summary="Sum")
        body = client.get(f"/articles/{article_id}/reader").get_data(as_text=True)

        assert "<p>First paragraph of the story.</p>" in body
        assert fetch_row(app, article_id)["full_text"] == LONG_TEXT
        network[2].assert_not_called()

    def test_saved_article_falls_back_while_pending(self, app, client, feed_id, network):
        network[1].return_value = None
        article_id = insert_article(app, feed_id, content="<p>Feed body</p>")
        body = client.get(f"/articles/{article_id}/reader").get_data(as_text=True)
        assert "<p>Feed body</p>" in body
        assert "still being fetched" in body

    def test_unsaved_article_failure_shows_failed_notice(self, app, client, feed_id, network):
        network[1].return_value = None
        article_id = insert_article(app, feed_id, is_saved=False, summary="Sum")
        body = client.get(f"/articles/{article_id}/reader").get_data(as_text=True)
        assert "get the full article" in body
        assert "still being fetched" not in body

    def test_no_fetch_after_max_attempts(self, app, client, feed_id, network):
        article_id = insert_article(app, feed_id, summary="Sum",
                                    extract_attempts=archive_service.MAX_EXTRACT_ATTEMPTS)
        body = client.get(f"/articles/{article_id}/reader").get_data(as_text=True)
        assert "get the full article" in body
        network[0].assert_not_called()

    def test_every_article_has_reader_button(self, app, client, feed_id):
        article_id = insert_article(app, feed_id, is_saved=False, is_read=1)
        body = client.get("/?unread=0").get_data(as_text=True)
        assert f'href="/articles/{article_id}/reader"' in body

    def test_escapes_extracted_text(self, app, client, feed_id):
        article_id = insert_article(app, feed_id, full_text="<script>alert(1)</script>")
        body = client.get(f"/articles/{article_id}/reader").get_data(as_text=True)
        assert "<script>alert(1)</script>" not in body

    def test_missing_article_is_404(self, client):
        assert client.get("/articles/9999/reader").status_code == 404

    def test_saved_view_links_to_reader(self, app, client, feed_id, network):
        article_id = insert_article(app, feed_id)
        body = client.get("/saved").get_data(as_text=True)
        assert f"/articles/{article_id}/reader" in body


class TestMigration:
    def test_new_columns_exist(self, app):
        with app.app_context():
            columns = {row[1] for row in get_db().execute("PRAGMA table_info(articles)")}
        assert {"full_text", "extract_attempts", "wayback_saved_at"} <= columns
