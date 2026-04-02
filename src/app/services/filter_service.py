import re
import sqlite3
from src.app.database import get_db
from src.app.models import Filter, Article

SQLITE_VAR_LIMIT = 999

FILTER_UPDATABLE_COLUMNS = {"name", "pattern", "target", "is_active"}


def _chunked_update_is_read(db, article_ids: list[int]) -> None:
    for i in range(0, len(article_ids), SQLITE_VAR_LIMIT):
        chunk = article_ids[i:i + SQLITE_VAR_LIMIT]
        placeholders = ",".join("?" for _ in chunk)
        db.execute(
            "UPDATE articles SET is_read = 1 WHERE id IN ({})".format(placeholders),
            chunk
        )


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

    field_values = {}
    if name is not None:
        field_values["name"] = name.strip()
    if pattern is not None:
        field_values["pattern"] = pattern.strip()
    if target is not None:
        field_values["target"] = target
    if is_active is not None:
        field_values["is_active"] = 1 if is_active else 0

    if not field_values:
        return existing, None

    for col in field_values:
        if col not in FILTER_UPDATABLE_COLUMNS:
            return None, f"Invalid field: {col}"

    set_clause = ", ".join(f"{col} = ?" for col in field_values)
    params = list(field_values.values()) + [filter_id]
    db.execute(f"UPDATE filters SET {set_clause} WHERE id = ?", params)
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
        SELECT a.id, a.title, a.summary, a.is_read
        FROM articles a
        WHERE a.is_saved = 0
          AND a.id NOT IN (
              SELECT article_id FROM filter_matches WHERE filter_id = ?
          )
    """, (filter_obj.id,)).fetchall()

    match_ids = []
    unread_matched_ids = []
    compiled = re.compile(filter_obj.pattern, re.IGNORECASE)

    for row in rows:
        if article_matches_filter(row["title"], row["summary"], compiled, filter_obj.target):
            match_ids.append(row["id"])
            if not row["is_read"]:
                unread_matched_ids.append(row["id"])

    if match_ids:
        db.executemany(
            "INSERT OR IGNORE INTO filter_matches (article_id, filter_id) VALUES (?, ?)",
            [(aid, filter_obj.id) for aid in match_ids]
        )
        if unread_matched_ids:
            _chunked_update_is_read(db, unread_matched_ids)
        db.commit()

    return len(match_ids)


def reapply_all_filters() -> int:
    db = get_db()

    remarked = db.execute("""
        UPDATE articles SET is_read = 1
        WHERE is_read = 0 AND is_saved = 0
          AND id IN (SELECT article_id FROM filter_matches)
    """)
    db.commit()
    remarked_count = remarked.rowcount

    compiled_filters = get_compiled_active_filters()
    if not compiled_filters:
        return remarked_count

    existing_matches = set()
    for row in db.execute("SELECT article_id, filter_id FROM filter_matches").fetchall():
        existing_matches.add((row["article_id"], row["filter_id"]))

    rows = db.execute("""
        SELECT a.id, a.title, a.summary, a.is_read
        FROM articles a
        WHERE a.is_saved = 0
    """).fetchall()

    new_match_rows = []
    unread_matched_ids = set()

    for row in rows:
        for f, compiled in compiled_filters:
            if (row["id"], f.id) in existing_matches:
                continue
            if article_matches_filter(row["title"], row["summary"], compiled, f.target):
                new_match_rows.append((row["id"], f.id))
                if not row["is_read"]:
                    unread_matched_ids.add(row["id"])

    if new_match_rows:
        db.executemany(
            "INSERT OR IGNORE INTO filter_matches (article_id, filter_id) VALUES (?, ?)",
            new_match_rows
        )

    if unread_matched_ids:
        _chunked_update_is_read(db, list(unread_matched_ids))

    if new_match_rows or unread_matched_ids:
        db.commit()

    return remarked_count + len(new_match_rows)


def clear_filter_matches(filter_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM filter_matches WHERE filter_id = ?", (filter_id,))
    db.commit()


def get_compiled_active_filters() -> list[tuple[Filter, re.Pattern]]:
    compiled = []
    for f in get_active_filters():
        try:
            compiled.append((f, re.compile(f.pattern, re.IGNORECASE)))
        except re.error:
            continue
    return compiled


def apply_filters_to_articles(
    articles: list[tuple[int, str | None, str | None]],
    compiled_filters: list[tuple[Filter, re.Pattern]] | None = None
) -> int:
    if compiled_filters is None:
        compiled_filters = get_compiled_active_filters()

    if not compiled_filters or not articles:
        return 0

    db = get_db()
    match_rows = []
    matched_article_ids = set()

    for article_id, title, summary in articles:
        for f, compiled in compiled_filters:
            if article_matches_filter(title, summary, compiled, f.target):
                match_rows.append((article_id, f.id))
                matched_article_ids.add(article_id)

    if match_rows:
        db.executemany(
            "INSERT OR IGNORE INTO filter_matches (article_id, filter_id) VALUES (?, ?)",
            match_rows
        )
        _chunked_update_is_read(db, list(matched_article_ids))
        db.commit()

    return len(matched_article_ids)


def apply_filters_to_article(article_id: int, title: str | None, summary: str | None,
                              compiled_filters: list[tuple[Filter, re.Pattern]] | None = None) -> list[int]:
    if compiled_filters is None:
        compiled_filters = get_compiled_active_filters()

    matched_filter_ids = []

    for f, compiled in compiled_filters:
        if article_matches_filter(title, summary, compiled, f.target):
            matched_filter_ids.append(f.id)

    if matched_filter_ids:
        db = get_db()
        db.executemany(
            "INSERT OR IGNORE INTO filter_matches (article_id, filter_id) VALUES (?, ?)",
            [(article_id, fid) for fid in matched_filter_ids]
        )
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
