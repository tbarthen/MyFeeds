from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash

from src.app.services import feed_service, article_service, filter_service, settings_service, opml_service


bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    feeds = feed_service.get_all_feeds()
    feed_id = request.args.get("feed_id", type=int)
    unread_only = request.args.get("unread", "0") == "1"

    articles = article_service.get_articles(
        feed_id=feed_id,
        unread_only=unread_only
    )

    total_unread = article_service.get_unread_count()
    saved_count = article_service.get_saved_count()
    filtered_count = filter_service.get_total_filtered_count()

    return render_template(
        "index.html",
        feeds=feeds,
        articles=articles,
        selected_feed_id=feed_id,
        unread_only=unread_only,
        total_unread=total_unread,
        saved_count=saved_count,
        filtered_count=filtered_count
    )


@bp.route("/feeds/add", methods=["POST"])
def add_feed():
    url = request.form.get("url", "").strip()
    if not url:
        flash("Please enter a feed URL", "error")
        return redirect(url_for("main.index"))

    feed, error = feed_service.add_feed(url)
    if error:
        if "already exists" in error.lower():
            flash(f"This feed is already in your subscriptions", "info")
        else:
            flash(f"Couldn't add this URL — {error}", "warning")
    else:
        flash(f"Added: {feed.title}", "success")
    return redirect(url_for("main.index"))


@bp.route("/feeds/<int:feed_id>/delete", methods=["POST"])
def delete_feed(feed_id: int):
    feed_service.delete_feed(feed_id)
    return redirect(url_for("main.index"))


@bp.route("/feeds/<int:feed_id>/refresh", methods=["POST"])
def refresh_feed(feed_id: int):
    feed_service.refresh_feed(feed_id)
    return redirect(url_for("main.index", feed_id=feed_id))


@bp.route("/feeds/refresh-all", methods=["POST"])
def refresh_all_feeds():
    feed_service.refresh_all_feeds()
    return redirect(url_for("main.index"))


@bp.route("/articles/<int:article_id>/read", methods=["POST"])
def mark_read(article_id: int):
    article_service.mark_article_read(article_id, is_read=True)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"success": True})
    return redirect(request.referrer or url_for("main.index"))


@bp.route("/articles/<int:article_id>/unread", methods=["POST"])
def mark_unread(article_id: int):
    article_service.mark_article_read(article_id, is_read=False)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"success": True})
    return redirect(request.referrer or url_for("main.index"))


@bp.route("/articles/mark-all-read", methods=["POST"])
def mark_all_read():
    feed_id = request.args.get("feed_id", type=int)
    article_service.mark_all_read(feed_id)
    return redirect(request.referrer or url_for("main.index"))


@bp.route("/api/feeds")
def api_feeds():
    feeds = feed_service.get_all_feeds()
    return jsonify([{
        "id": f.id,
        "title": f.title,
        "url": f.url,
        "unread_count": f.unread_count,
        "fetch_error_count": f.fetch_error_count,
        "last_error": f.last_error
    } for f in feeds])


@bp.route("/api/articles")
def api_articles():
    feed_id = request.args.get("feed_id", type=int)
    unread_only = request.args.get("unread", "0") == "1"

    articles = article_service.get_articles(feed_id=feed_id, unread_only=unread_only)
    return jsonify([{
        "id": a.id,
        "title": a.title,
        "summary": a.summary,
        "url": a.url,
        "feed_title": a.feed_title,
        "published_at": a.published_at.isoformat() if a.published_at else None,
        "is_read": a.is_read,
        "is_saved": a.is_saved
    } for a in articles])


@bp.route("/filters")
def filters_page():
    filters = filter_service.get_all_filters()
    filter_counts = {f.id: filter_service.get_filter_match_count(f.id) for f in filters}
    total_unread = article_service.get_unread_count()
    saved_count = article_service.get_saved_count()
    filtered_count = filter_service.get_total_filtered_count()
    return render_template(
        "filters.html",
        filters=filters,
        filter_counts=filter_counts,
        total_unread=total_unread,
        saved_count=saved_count,
        filtered_count=filtered_count
    )


@bp.route("/filters/add", methods=["POST"])
def add_filter():
    name = request.form.get("name", "").strip()
    pattern = request.form.get("pattern", "").strip()
    target = request.form.get("target", "both")

    filter_service.create_filter(name, pattern, target)
    return redirect(url_for("main.filters_page"))


@bp.route("/filters/<int:filter_id>/edit", methods=["POST"])
def edit_filter(filter_id: int):
    name = request.form.get("name")
    pattern = request.form.get("pattern")
    target = request.form.get("target")
    is_active = request.form.get("is_active") == "1"

    filter_service.update_filter(
        filter_id,
        name=name,
        pattern=pattern,
        target=target,
        is_active=is_active
    )
    return redirect(url_for("main.filters_page"))


@bp.route("/filters/<int:filter_id>/toggle", methods=["POST"])
def toggle_filter(filter_id: int):
    f = filter_service.get_filter_by_id(filter_id)
    if f:
        filter_service.update_filter(filter_id, is_active=not f.is_active)
    return redirect(url_for("main.filters_page"))


@bp.route("/filters/<int:filter_id>/delete", methods=["POST"])
def delete_filter(filter_id: int):
    filter_service.delete_filter(filter_id)
    return redirect(url_for("main.filters_page"))


@bp.route("/filtered")
def filtered_view():
    filtered_by_rule = filter_service.get_filtered_articles_by_rule()
    total_filtered = filter_service.get_total_filtered_count()
    total_unread = article_service.get_unread_count()
    saved_count = article_service.get_saved_count()
    return render_template(
        "filtered.html",
        filtered_by_rule=filtered_by_rule,
        total_filtered=total_filtered,
        total_unread=total_unread,
        saved_count=saved_count,
        filtered_count=total_filtered
    )


@bp.route("/api/filters")
def api_filters():
    filters = filter_service.get_all_filters()
    return jsonify([{
        "id": f.id,
        "name": f.name,
        "pattern": f.pattern,
        "target": f.target,
        "is_active": f.is_active,
        "match_count": filter_service.get_filter_match_count(f.id)
    } for f in filters])


@bp.route("/articles/<int:article_id>/save", methods=["POST"])
def toggle_save(article_id: int):
    new_state = article_service.toggle_saved(article_id)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"success": True, "is_saved": new_state})
    return redirect(request.referrer or url_for("main.index"))


@bp.route("/saved")
def saved_articles():
    feeds = feed_service.get_all_feeds()
    articles = article_service.get_articles(saved_only=True)
    total_unread = article_service.get_unread_count()
    saved_count = article_service.get_saved_count()
    filtered_count = filter_service.get_total_filtered_count()

    return render_template(
        "index.html",
        feeds=feeds,
        articles=articles,
        selected_feed_id=None,
        unread_only=False,
        total_unread=total_unread,
        saved_count=saved_count,
        filtered_count=filtered_count,
        view_mode="saved"
    )


@bp.route("/settings")
def settings_page():
    settings = settings_service.get_all_settings()
    total_unread = article_service.get_unread_count()
    saved_count = article_service.get_saved_count()
    filtered_count = filter_service.get_total_filtered_count()
    return render_template(
        "settings.html",
        settings=settings,
        total_unread=total_unread,
        saved_count=saved_count,
        filtered_count=filtered_count
    )


@bp.route("/settings/save", methods=["POST"])
def save_settings():
    refresh_interval = request.form.get("refresh_interval", "30")
    auto_refresh = "1" if request.form.get("auto_refresh") else "0"

    try:
        interval = int(refresh_interval)
        if interval < 5:
            interval = 5
        elif interval > 1440:
            interval = 1440
    except ValueError:
        interval = 30

    settings_service.set_setting("refresh_interval_minutes", str(interval))
    settings_service.set_setting("auto_refresh_enabled", auto_refresh)

    if auto_refresh == "1":
        from src.app.scheduler import update_scheduler_interval
        update_scheduler_interval(interval)

    return redirect(url_for("main.settings_page"))


@bp.route("/settings/import-opml", methods=["POST"])
def import_opml():
    if "opml_file" not in request.files:
        flash("No file uploaded", "error")
        return redirect(url_for("main.settings_page"))

    file = request.files["opml_file"]
    if file.filename == "":
        flash("No file selected", "error")
        return redirect(url_for("main.settings_page"))

    content = file.read()
    imported, skipped, errors = opml_service.import_opml(content)

    if imported > 0:
        flash(f"Imported {imported} feed(s)", "success")
    if skipped > 0:
        flash(f"Skipped {skipped} existing feed(s)", "info")
    if errors:
        for error in errors[:5]:
            flash(error, "error")

    return redirect(url_for("main.settings_page"))
