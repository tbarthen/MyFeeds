import logging
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()
_app = None


def refresh_all_feeds_job():
    if _app is None:
        return

    with _app.app_context():
        from src.app.services import feed_service, settings_service

        if not settings_service.is_auto_refresh_enabled():
            return

        start = time.monotonic()
        results = feed_service.refresh_all_feeds()
        elapsed = time.monotonic() - start

        total_new = sum(count for count, _ in results.values())
        errors = [(fid, err) for fid, (_, err) in results.items()
                  if err and not err.startswith("skipped") and err != "not_modified"]
        skipped = sum(1 for _, err in results.values() if err and err.startswith("skipped"))
        not_modified = sum(1 for _, err in results.values() if err == "not_modified")

        logger.info(
            "Feed refresh complete: %d feeds, %d new articles, %d not modified, "
            "%d skipped, %d errors, %.1fs elapsed",
            len(results), total_new, not_modified, skipped,
            len(errors), elapsed
        )
        for fid, err in errors:
            logger.warning("Feed %d error: %s", fid, err)


def init_scheduler(app):
    global _app
    _app = app

    if scheduler.running:
        return

    with app.app_context():
        from src.app.services import settings_service
        interval = settings_service.get_refresh_interval()

    scheduler.add_job(
        refresh_all_feeds_job,
        trigger=IntervalTrigger(minutes=interval),
        id="refresh_feeds",
        replace_existing=True
    )

    scheduler.start()


def update_scheduler_interval(minutes: int):
    if not scheduler.running:
        return

    scheduler.reschedule_job(
        "refresh_feeds",
        trigger=IntervalTrigger(minutes=minutes)
    )


def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
