import re
from src.app.database import get_db
from src.app.models import Filter, Article


def get_all_filters() -> list[Filter]:
    db = get_db()
    rows = db.execute("""
        SELECT * FROM filters ORDER BY name COLLATE NOCASE
    """).fetchall()
    return [Filter.from_row(row) for row in rows]


def get_active_filters() -> list[Filter]:
    db = get_db()
    rows = db.execute("""
        SELECT * FROM filters WHERE is_active = 1 ORDER BY name COLLATE NOCASE
    """).fetchall()
    return [Filter.from_row(row) for row in rows]


def get_filter_by_id(filter_id: int) -> Filter | None:
    db = get_db()
    row = db.execute("SELECT * FROM filters WHERE id = ?", (filter_id,)).fetchone()
    return Filter.from_row(row) if row else None


def create_filter(name: str, pattern: str, target: str) -> tuple[Filter | None, str | None]:
    if not name or not name.strip():
        return None, "Name is required"

    if not pattern or not pattern.strip():
        return None, "Pattern is required"

    if target not in ("title", "summary", "both"):
        return None, "Target must be 'title', 'summary', or 'both'"

    if not is_valid_regex(pattern):
        return None, "Invalid regex pattern"

    db = get_db()
    cursor = db.execute(
        "INSERT INTO filters (name, pattern, target) VALUES (?, ?, ?)",
        (name.strip(), pattern.strip(), target)
    )
    db.commit()

    new_filter = get_filter_by_id(cursor.lastrowid)

    apply_filter_to_existing_articles(new_filter)

    return new_filter, None


def update_filter(
    filter_id: int,
    name: str | None = None,
    pattern: str | None = None,
    target: str | None = None,
    is_active: bool | None = None
) -> tuple[Filter | None, str | None]:
    existing = get_filter_by_id(filter_id)
    if not existing:
        return None, "Filter not found"

    if pattern is not None and not is_valid_regex(pattern):
        return None, "Invalid regex pattern"

    if target is not None and target not in ("title", "summary", "both"):
        return None, "Target must be 'title', 'summary', or 'both'"

    db = get_db()

    updates = []
    params = []

    if name is not None:
        updates.append("name = ?")
        params.append(name.strip())

    if pattern is not None:
        updates.append("pattern = ?")
        params.append(pattern.strip())

    if target is not None:
        updates.append("target = ?")
        params.append(target)

    if is_active is not None:
        updates.append("is_active = ?")
        params.append(1 if is_active else 0)

    if not updates:
        return existing, None

    params.append(filter_id)
    db.execute(f"UPDATE filters SET {', '.join(updates)} WHERE id = ?", params)
    db.commit()

    updated = get_filter_by_id(filter_id)

    pattern_changed = pattern is not None and pattern != existing.pattern
    target_changed = target is not None and target != existing.target
    reactivated = is_active is True and not existing.is_active

    if pattern_changed or target_changed or reactivated:
        clear_filter_matches(filter_id)
        apply_filter_to_existing_articles(updated)

    return updated, None


def delete_filter(filter_id: int) -> bool:
    db = get_db()
    cursor = db.execute("DELETE FROM filters WHERE id = ?", (filter_id,))
    db.commit()
    return cursor.rowcount > 0


def is_valid_regex(pattern: str) -> bool:
    try:
        re.compile(pattern)
        return True
    except re.error:
        return False


def apply_filter_to_existing_articles(filter_obj: Filter) -> int:
    if not filter_obj.is_active:
        return 0

    db = get_db()

    rows = db.execute("""
        SELECT a.id, a.title, a.summary
        FROM articles a
        WHERE a.is_read = 0 AND a.is_saved = 0
          AND a.id NOT IN (
              SELECT article_id FROM filter_matches WHERE filter_id = ?
          )
    """, (filter_obj.id,)).fetchall()

    match_count = 0
    matched_ids = []
    compiled = re.compile(filter_obj.pattern, re.IGNORECASE)

    for row in rows:
        if article_matches_filter(row["title"], row["summary"], compiled, filter_obj.target):
            record_filter_match(row["id"], filter_obj.id)
            matched_ids.append(row["id"])
            match_count += 1

    if matched_ids:
        placeholders = ",".join("?" * len(matched_ids))
        db.execute(f"UPDATE articles SET is_read = 1 WHERE id IN ({placeholders})", matched_ids)
        db.commit()

    return match_count


def clear_filter_matches(filter_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM filter_matches WHERE filter_id = ?", (filter_id,))
    db.commit()


def apply_filters_to_article(article_id: int, title: str | None, summary: str | None) -> list[int]:
    filters = get_active_filters()
    matched_filter_ids = []

    for f in filters:
        compiled = re.compile(f.pattern, re.IGNORECASE)
        if article_matches_filter(title, summary, compiled, f.target):
            record_filter_match(article_id, f.id)
            matched_filter_ids.append(f.id)

    if matched_filter_ids:
        db = get_db()
        db.execute("UPDATE articles SET is_read = 1 WHERE id = ?", (article_id,))
        db.commit()

    return matched_filter_ids


def article_matches_filter(
    title: str | None,
    summary: str | None,
    compiled_pattern: re.Pattern,
    target: str
) -> bool:
    title = title or ""
    summary = summary or ""

    if target == "title":
        return bool(compiled_pattern.search(title))
    elif target == "summary":
        return bool(compiled_pattern.search(summary))
    else:
        return bool(compiled_pattern.search(title) or compiled_pattern.search(summary))


def record_filter_match(article_id: int, filter_id: int) -> None:
    db = get_db()
    try:
        db.execute(
            "INSERT INTO filter_matches (article_id, filter_id) VALUES (?, ?)",
            (article_id, filter_id)
        )
        db.commit()
    except Exception:
        pass


def get_filtered_articles_by_rule() -> list[tuple[Filter, list[Article]]]:
    db = get_db()
    filters = get_all_filters()
    result = []

    for f in filters:
        rows = db.execute("""
            SELECT a.*, feeds.title as feed_title
            FROM articles a
            JOIN filter_matches fm ON a.id = fm.article_id
            JOIN feeds ON a.feed_id = feeds.id
            WHERE fm.filter_id = ?
            ORDER BY a.published_at DESC
        """, (f.id,)).fetchall()

        if rows:
            result.append((f, [Article.from_row(row) for row in rows]))

    return result


def get_filter_match_count(filter_id: int) -> int:
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) as count FROM filter_matches WHERE filter_id = ?",
        (filter_id,)
    ).fetchone()
    return row["count"]


def get_total_filtered_count() -> int:
    db = get_db()
    row = db.execute(
        "SELECT COUNT(DISTINCT article_id) as count FROM filter_matches"
    ).fetchone()
    return row["count"]
