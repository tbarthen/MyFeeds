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
    etag: str | None = None
    last_modified: str | None = None
    hidden: bool = False
    unsubscribed: bool = False
    keep_pattern: str | None = None

    @classmethod
    def from_row(cls, row) -> "Feed":
        keys = row.keys()
        return cls(
            id=row["id"],
            url=row["url"],
            title=row["title"],
            site_url=row["site_url"],
            last_fetched=parse_datetime(row["last_fetched"]),
            fetch_error_count=row["fetch_error_count"],
            last_error=row["last_error"],
            created_at=parse_datetime(row["created_at"]),
            unread_count=row["unread_count"] if "unread_count" in keys else 0,
            etag=row["etag"] if "etag" in keys else None,
            last_modified=row["last_modified"] if "last_modified" in keys else None,
            hidden=bool(row["hidden"]) if "hidden" in keys else False,
            unsubscribed=bool(row["unsubscribed"]) if "unsubscribed" in keys else False,
            keep_pattern=row["keep_pattern"] if "keep_pattern" in keys else None,
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
    is_exempt: bool = False
    created_at: datetime | None = None
    feed_title: str | None = None
    matched_text: str | None = None
    full_text: str | None = None
    extract_attempts: int = 0
    wayback_saved_at: datetime | None = None

    @classmethod
    def from_row(cls, row) -> "Article":
        keys = row.keys()
        return cls(
            id=row["id"],
            feed_id=row["feed_id"],
            guid=row["guid"],
            title=row["title"],
            summary=row["summary"],
            content=row["content"],
            url=row["url"],
            image_url=row["image_url"] if "image_url" in keys else None,
            published_at=parse_datetime(row["published_at"]),
            is_read=bool(row["is_read"]),
            is_saved=bool(row["is_saved"]),
            is_exempt=bool(row["is_exempt"]) if "is_exempt" in keys else False,
            created_at=parse_datetime(row["created_at"]),
            feed_title=row["feed_title"] if "feed_title" in keys else None,
            matched_text=row["matched_text"] if "matched_text" in keys else None,
            full_text=row["full_text"] if "full_text" in keys else None,
            extract_attempts=row["extract_attempts"] if "extract_attempts" in keys else 0,
            wayback_saved_at=parse_datetime(row["wayback_saved_at"]) if "wayback_saved_at" in keys else None,
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
