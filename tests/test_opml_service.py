from unittest.mock import patch, MagicMock

import pytest

from src.app.services import opml_service


SAMPLE_OPML = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="1.0">
    <head>
        <title>My Feeds</title>
    </head>
    <body>
        <outline text="Tech" title="Tech">
            <outline type="rss" text="Hacker News" title="Hacker News"
                     xmlUrl="https://hnrss.org/frontpage"
                     htmlUrl="https://news.ycombinator.com/"/>
        </outline>
        <outline type="rss" text="Example Feed" title="Example Feed"
                 xmlUrl="https://example.com/feed.xml"/>
    </body>
</opml>
"""

FEEDLY_OPML = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="1.0">
    <head>
        <title>Feedly Export</title>
    </head>
    <body>
        <outline text="Tech" title="Tech">
            <outline type="rss" text="The Verge"
                     xmlUrl="https://www.theverge.com/rss/index.xml"
                     htmlUrl="https://www.theverge.com"/>
            <outline type="rss" text="Ars Technica"
                     xmlUrl="https://feeds.arstechnica.com/arstechnica/index"
                     htmlUrl="https://arstechnica.com"/>
        </outline>
    </body>
</opml>
"""

INVALID_OPML = """not valid xml at all"""


class TestParseOPML:
    def test_parse_valid_opml(self):
        feeds = opml_service.parse_opml(SAMPLE_OPML)

        assert len(feeds) == 2
        assert feeds[0].title == "Hacker News"
        assert feeds[0].xml_url == "https://hnrss.org/frontpage"
        assert feeds[0].html_url == "https://news.ycombinator.com/"
        assert feeds[1].title == "Example Feed"

    def test_parse_feedly_opml(self):
        feeds = opml_service.parse_opml(FEEDLY_OPML)

        assert len(feeds) == 2
        titles = [f.title for f in feeds]
        assert "The Verge" in titles
        assert "Ars Technica" in titles

    def test_parse_invalid_opml(self):
        feeds = opml_service.parse_opml(INVALID_OPML)
        assert feeds == []

    def test_parse_empty_opml(self):
        feeds = opml_service.parse_opml("")
        assert feeds == []

    def test_parse_opml_bytes(self):
        feeds = opml_service.parse_opml(SAMPLE_OPML.encode("utf-8"))
        assert len(feeds) == 2


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
        parsed["entries"] = []
        parsed["bozo"] = False
        mock_parse.return_value = parsed

        yield mock_req, mock_parse


class TestImportOPML:
    def test_import_opml_success(self, app, mock_feed_fetch):
        with app.app_context():
            imported, skipped, errors = opml_service.import_opml(SAMPLE_OPML)

            assert imported == 2
            assert skipped == 0
            assert len(errors) == 0

    def test_import_opml_skips_duplicates(self, app, mock_feed_fetch):
        with app.app_context():
            opml_service.import_opml(SAMPLE_OPML)

            imported, skipped, errors = opml_service.import_opml(SAMPLE_OPML)

            assert imported == 0
            assert skipped == 2

    def test_import_invalid_opml(self, app):
        with app.app_context():
            imported, skipped, errors = opml_service.import_opml(INVALID_OPML)

            assert imported == 0
            assert skipped == 0
            assert len(errors) == 1
            assert "No valid feeds found" in errors[0]
