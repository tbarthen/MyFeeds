from dataclasses import dataclass
from datetime import datetime


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


@dataclass
class Feed:
    id: int | None
    url: str
    title: str | None = None
    site_url: str | None = None
    last_fetched: datetime | None = None
    fetch_error_count: int = 0
    last_error: str | None = None
    created_at: datetime | None = None
    unread_count: int = 0

    @classmethod
    def from_row(cls, row) -> "Feed":
        return cls(
            id=row["id"],
            url=row["url"],
            title=row["title"],
            site_url=row["site_url"],
            last_fetched=parse_datetime(row["last_fetched"]),
            fetch_error_count=row["fetch_error_count"],
            last_error=row["last_error"],
            created_at=parse_datetime(row["created_at"]),
            unread_count=row["unread_count"] if "unread_count" in row.keys() else 0
        )


@dataclass
class Article:
    id: int | None
    feed_id: int
    guid: str
    title: str | None = None
    summary: str | None = None
    content: str | None = None
    url: str | None = None
    image_url: str | None = None
    published_at: datetime | None = None
    is_read: bool = False
    is_saved: bool = False
    created_at: datetime | None = None
    feed_title: str | None = None

    @classmethod
    def from_row(cls, row) -> "Article":
        return cls(
            id=row["id"],
            feed_id=row["feed_id"],
            guid=row["guid"],
            title=row["title"],
            summary=row["summary"],
            content=row["content"],
            url=row["url"],
            image_url=row["image_url"] if "image_url" in row.keys() else None,
            published_at=parse_datetime(row["published_at"]),
            is_read=bool(row["is_read"]),
            is_saved=bool(row["is_saved"]),
            created_at=parse_datetime(row["created_at"]),
            feed_title=row["feed_title"] if "feed_title" in row.keys() else None
        )


@dataclass
class Filter:
    id: int | None
    name: str
    pattern: str
    target: str
    is_active: bool = True
    created_at: datetime | None = None

    @classmethod
    def from_row(cls, row) -> "Filter":
        return cls(
            id=row["id"],
            name=row["name"],
            pattern=row["pattern"],
            target=row["target"],
            is_active=bool(row["is_active"]),
            created_at=parse_datetime(row["created_at"])
        )
