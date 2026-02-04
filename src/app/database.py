import re
import sqlite3
from contextlib import contextmanager
from flask import Flask, g, current_app


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


@contextmanager
def get_db_connection(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db(app: Flask) -> None:
    app.teardown_appcontext(close_db)

    with app.app_context():
        db = get_db()
        db.executescript(SCHEMA)
        db.commit()
        _run_migrations(db)


def _run_migrations(db: sqlite3.Connection) -> None:
    cursor = db.execute("PRAGMA table_info(articles)")
    columns = [row[1] for row in cursor.fetchall()]
    if "image_url" not in columns:
        db.execute("ALTER TABLE articles ADD COLUMN image_url TEXT")
        db.commit()

    _backfill_article_images(db)


def _backfill_article_images(db: sqlite3.Connection) -> None:
    """Extract images from content/summary for articles missing image_url."""
    articles = db.execute("""
        SELECT id, content, summary FROM articles
        WHERE image_url IS NULL AND (content IS NOT NULL OR summary IS NOT NULL)
    """).fetchall()

    for article in articles:
        html_content = article["content"] or article["summary"] or ""
        if html_content:
            img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html_content)
            if img_match:
                db.execute(
                    "UPDATE articles SET image_url = ? WHERE id = ?",
                    (img_match.group(1), article["id"])
                )

    db.commit()


SCHEMA = """
CREATE TABLE IF NOT EXISTS feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    title TEXT,
    site_url TEXT,
    last_fetched DATETIME,
    fetch_error_count INTEGER DEFAULT 0,
    last_error TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_id INTEGER NOT NULL,
    guid TEXT NOT NULL,
    title TEXT,
    summary TEXT,
    content TEXT,
    url TEXT,
    image_url TEXT,
    published_at DATETIME,
    is_read BOOLEAN DEFAULT 0,
    is_saved BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (feed_id) REFERENCES feeds(id) ON DELETE CASCADE,
    UNIQUE(feed_id, guid)
);

CREATE TABLE IF NOT EXISTS filters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    pattern TEXT NOT NULL,
    target TEXT NOT NULL CHECK(target IN ('title', 'summary', 'both')),
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS filter_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL,
    filter_id INTEGER NOT NULL,
    matched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
    FOREIGN KEY (filter_id) REFERENCES filters(id) ON DELETE CASCADE,
    UNIQUE(article_id, filter_id)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_articles_feed_id ON articles(feed_id);
CREATE INDEX IF NOT EXISTS idx_articles_is_read ON articles(is_read);
CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at);
CREATE INDEX IF NOT EXISTS idx_articles_is_saved ON articles(is_saved);
CREATE INDEX IF NOT EXISTS idx_filter_matches_article_id ON filter_matches(article_id);
CREATE INDEX IF NOT EXISTS idx_filter_matches_filter_id ON filter_matches(filter_id);
"""
