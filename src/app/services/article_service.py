from src.app.database import get_db
from src.app.models import Article


def get_articles(
    feed_id: int | None = None,
    unread_only: bool = False,
    saved_only: bool = False,
    limit: int = 50,
    offset: int = 0
) -> list[Article]:
    db = get_db()

    query = """
        SELECT a.*, f.title as feed_title
        FROM articles a
        JOIN feeds f ON a.feed_id = f.id
        WHERE 1=1
    """
    params = []

    if feed_id is not None:
        query += " AND a.feed_id = ?"
        params.append(feed_id)

    if unread_only:
        query += " AND a.is_read = 0"

    if saved_only:
        query += " AND a.is_saved = 1"

    query += " ORDER BY a.published_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = db.execute(query, params).fetchall()
    return [Article.from_row(row) for row in rows]


def get_article_by_id(article_id: int) -> Article | None:
    db = get_db()
    row = db.execute("""
        SELECT a.*, f.title as feed_title
        FROM articles a
        JOIN feeds f ON a.feed_id = f.id
        WHERE a.id = ?
    """, (article_id,)).fetchone()
    return Article.from_row(row) if row else None


def mark_article_read(article_id: int, is_read: bool = True) -> bool:
    db = get_db()
    cursor = db.execute(
        "UPDATE articles SET is_read = ? WHERE id = ?",
        (1 if is_read else 0, article_id)
    )
    db.commit()
    return cursor.rowcount > 0


def mark_all_read(feed_id: int | None = None) -> int:
    db = get_db()

    if feed_id is not None:
        cursor = db.execute(
            "UPDATE articles SET is_read = 1 WHERE feed_id = ? AND is_read = 0",
            (feed_id,)
        )
    else:
        cursor = db.execute("UPDATE articles SET is_read = 1 WHERE is_read = 0")

    db.commit()
    return cursor.rowcount


def toggle_saved(article_id: int) -> bool | None:
    db = get_db()
    row = db.execute("SELECT is_saved FROM articles WHERE id = ?", (article_id,)).fetchone()
    if not row:
        return None

    new_value = 0 if row["is_saved"] else 1
    db.execute("UPDATE articles SET is_saved = ? WHERE id = ?", (new_value, article_id))
    db.commit()
    return bool(new_value)


def get_unread_count(feed_id: int | None = None) -> int:
    db = get_db()

    if feed_id is not None:
        row = db.execute(
            "SELECT COUNT(*) as count FROM articles WHERE feed_id = ? AND is_read = 0",
            (feed_id,)
        ).fetchone()
    else:
        row = db.execute("SELECT COUNT(*) as count FROM articles WHERE is_read = 0").fetchone()

    return row["count"]


def get_saved_count() -> int:
    db = get_db()
    row = db.execute("SELECT COUNT(*) as count FROM articles WHERE is_saved = 1").fetchone()
    return row["count"]
