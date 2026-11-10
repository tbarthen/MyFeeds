import re
import sqlite3
from src.app.database import get_db
from src.app.models import Filter, Article

SQLITE_VAR_LIMIT = 999

FILTER_UPDATABLE_COLUMNS = {"name", "pattern", "target", "is_active"}

HTML_TAG = re.compile(r"<[^>]+>")
WHITESPACE = re.compile(r"\s+")

MatchRow = tuple[int, int, str]


def _chunked_update_is_read(db, article_ids: list[int]) -> None:
    for i in range(0, len(article_ids), SQLITE_VAR_LIMIT):
        chunk = article_ids[i:i + SQLITE_VAR_LIMIT]
        placeholders = ",".join("?" for _ in chunk)
        db.execute(
            "UPDATE articles SET is_read = 1, read_at = CURRENT_TIMESTAMP "
            "WHERE id IN ({})".format(placeholders),
            chunk
        )


def _record_matches(db, match_rows: list[MatchRow], article_ids_to_read: list[int]) -> None:
    """Persist (article_id, filter_id, matched_text) rows and mark the articles read."""
    if match_rows:
        db.executemany(
            "INSERT OR IGNORE INTO filter_matches (article_id, filter_id, matched_text) VALUES (?, ?, ?)",
            match_rows
        )
    if article_ids_to_read:
        _chunked_update_is_read(db, article_ids_to_read)
    if match_rows or article_ids_to_read:
        db.commit()


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
        WHERE a.is_saved = 0 AND a.is_exempt = 0
          AND a.id NOT IN (
              SELECT article_id FROM filter_matches WHERE filter_id = ?
          )
    """, (filter_obj.id,)).fetchall()

    match_rows = []
    unread_matched_ids = []
    compiled = re.compile(filter_obj.pattern, re.IGNORECASE)

    for row in rows:
        matched = find_match_text(row["title"], row["summary"], compiled, filter_obj.target)
        if matched is not None:
            match_rows.append((row["id"], filter_obj.id, matched))
            if not row["is_read"]:
                unread_matched_ids.append(row["id"])

    _record_matches(db, match_rows, unread_matched_ids)

    return len(match_rows)


def count_unread_matches(pattern: str, target: str) -> int:
    """Count unread, unsaved articles a pattern would catch if added as a filter.

    Mirrors what apply_filter_to_existing_articles moves to the Filtered view on
    add: saved and exempt articles are exempt, and already-filtered articles are
    read so they're excluded here. Assumes pattern is a valid regex.
    """
    db = get_db()
    rows = db.execute(
        "SELECT title, summary FROM articles WHERE is_saved = 0 AND is_exempt = 0 AND is_read = 0"
    ).fetchall()

    compiled = re.compile(pattern, re.IGNORECASE)
    return sum(
        1 for row in rows
        if article_matches_filter(row["title"], row["summary"], compiled, target)
    )


def reapply_all_filters() -> int:
    db = get_db()

    remarked = db.execute("""
        UPDATE articles SET is_read = 1, read_at = CURRENT_TIMESTAMP
        WHERE is_read = 0 AND is_saved = 0 AND is_exempt = 0
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
        WHERE a.is_saved = 0 AND a.is_exempt = 0
    """).fetchall()

    new_match_rows = []
    unread_matched_ids = set()

    for row in rows:
        for f, compiled in compiled_filters:
            if (row["id"], f.id) in existing_matches:
                continue
            matched = find_match_text(row["title"], row["summary"], compiled, f.target)
            if matched is not None:
                new_match_rows.append((row["id"], f.id, matched))
                if not row["is_read"]:
                    unread_matched_ids.add(row["id"])

    _record_matches(db, new_match_rows, list(unread_matched_ids))
    _backfill_matched_text(db, compiled_filters)

    return remarked_count + len(new_match_rows)


def _backfill_matched_text(db, compiled_filters: list[tuple[Filter, re.Pattern]]) -> None:
    """Fill matched_text for matches recorded before it was tracked."""
    by_filter_id = {f.id: (f, compiled) for f, compiled in compiled_filters}
    rows = db.execute("""
        SELECT fm.id, fm.filter_id, a.title, a.summary
        FROM filter_matches fm JOIN articles a ON a.id = fm.article_id
        WHERE fm.matched_text IS NULL
    """).fetchall()

    updates = []
    for row in rows:
        entry = by_filter_id.get(row["filter_id"])
        if entry is None:
            continue
        f, compiled = entry
        matched = find_match_text(row["title"], row["summary"], compiled, f.target)
        if matched is not None:
            updates.append((matched, row["id"]))

    if updates:
        db.executemany("UPDATE filter_matches SET matched_text = ? WHERE id = ?", updates)
        db.commit()


def clear_filter_matches(filter_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM filter_matches WHERE filter_id = ?", (filter_id,))
    db.commit()


def exempt_article(article_id: int) -> bool:
    """Rescue a false positive: drop its matches, mark unread, never filter it again."""
    db = get_db()
    cursor = db.execute(
        "UPDATE articles SET is_exempt = 1, is_read = 0, read_at = NULL WHERE id = ?",
        (article_id,)
    )
    if cursor.rowcount == 0:
        return False
    db.execute("DELETE FROM filter_matches WHERE article_id = ?", (article_id,))
    db.commit()
    return True


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
            matched = find_match_text(title, summary, compiled, f.target)
            if matched is not None:
                match_rows.append((article_id, f.id, matched))
                matched_article_ids.add(article_id)

    _record_matches(db, match_rows, list(matched_article_ids))

    return len(matched_article_ids)


def apply_filters_to_article(article_id: int, title: str | None, summary: str | None,
                              compiled_filters: list[tuple[Filter, re.Pattern]] | None = None) -> list[int]:
    if compiled_filters is None:
        compiled_filters = get_compiled_active_filters()

    match_rows = []
    for f, compiled in compiled_filters:
        matched = find_match_text(title, summary, compiled, f.target)
        if matched is not None:
            match_rows.append((article_id, f.id, matched))

    if match_rows:
        _record_matches(get_db(), match_rows, [article_id])

    return [filter_id for _, filter_id, _ in match_rows]


def strip_html(text: str | None) -> str:
    """Reduce HTML to its visible text so patterns never match tags, URLs or attributes."""
    if not text:
        return ""
    return WHITESPACE.sub(" ", HTML_TAG.sub(" ", text)).strip()


def find_match_text(
    title: str | None,
    summary: str | None,
    compiled_pattern: re.Pattern,
    target: str
) -> str | None:
    """Return the text the pattern matched in the targeted fields, or None."""
    fields = []
    if target in ("title", "both"):
        fields.append(title or "")
    if target in ("summary", "both"):
        fields.append(strip_html(summary))

    for text in fields:
        match = compiled_pattern.search(text)
        if match:
            return match.group(0)
    return None


def article_matches_filter(
    title: str | None,
    summary: str | None,
    compiled_pattern: re.Pattern,
    target: str
) -> bool:
    return find_match_text(title, summary, compiled_pattern, target) is not None


def get_filtered_articles_by_rule() -> list[tuple[Filter, list[Article]]]:
    db = get_db()
    filters = get_all_filters()
    result = []

    for f in filters:
        rows = db.execute("""
            SELECT a.*, feeds.title as feed_title, fm.matched_text
            FROM articles a
            JOIN filter_matches fm ON a.id = fm.article_id
            JOIN feeds ON a.feed_id = feeds.id
            WHERE fm.filter_id = ? AND feeds.hidden = 0
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
        "SELECT COUNT(DISTINCT fm.article_id) as count "
        "FROM filter_matches fm "
        "JOIN articles a ON a.id = fm.article_id "
        "JOIN feeds f ON a.feed_id = f.id "
        "WHERE f.hidden = 0"
    ).fetchone()
    return row["count"]
