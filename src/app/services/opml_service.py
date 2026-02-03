import xml.etree.ElementTree as ET
from dataclasses import dataclass

from src.app.services import feed_service


@dataclass
class OPMLFeed:
    title: str
    xml_url: str
    html_url: str | None = None


def parse_opml(content: str | bytes) -> list[OPMLFeed]:
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []

    feeds = []
    for outline in root.iter("outline"):
        xml_url = outline.get("xmlUrl")
        if xml_url:
            feeds.append(OPMLFeed(
                title=outline.get("title") or outline.get("text") or xml_url,
                xml_url=xml_url,
                html_url=outline.get("htmlUrl")
            ))

    return feeds


def import_opml(content: str | bytes) -> tuple[int, int, list[str]]:
    feeds = parse_opml(content)

    if not feeds:
        return 0, 0, ["No valid feeds found in OPML file"]

    imported = 0
    skipped = 0
    errors = []

    for opml_feed in feeds:
        result, error = feed_service.add_feed(opml_feed.xml_url)
        if result:
            imported += 1
        elif error == "Feed already exists":
            skipped += 1
        else:
            errors.append(f"{opml_feed.title}: {error}")

    return imported, skipped, errors
