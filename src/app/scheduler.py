import logging
import time
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()
_app = None

ON_DEMAND_POLL_SECONDS = 30
ON_DEMAND_COOLDOWN_MINUTES = 5


def _run_refresh(trigger: str):
    from src.app.services import feed_service

    start = time.monotonic()
    results = feed_service.refresh_all_feeds()
    elapsed = time.monotonic() - start

    total_new = sum(count for count, _ in results.values())
    errors = [(fid, err) for fid, (_, err) in results.items()
              if err and not err.startswith("skipped") and err != "not_modified"]
    skipped = sum(1 for _, err in results.values() if err and err.startswith("skipped"))
    not_modified = sum(1 for _, err in results.values() if err == "not_modified")

    logger.info(
        "Feed refresh complete (%s): %d feeds, %d new articles, %d not modified, "
        "%d skipped, %d errors, %.1fs elapsed",
        trigger, len(results), total_new, not_modified, skipped,
        len(errors), elapsed
    )
    for fid, err in errors:
        logger.warning("Feed %d error: %s", fid, err)


def refresh_all_feeds_job():
    if _app is None:
        return

    with _app.app_context():
        from src.app.services import settings_service

        if not settings_service.is_auto_refresh_enabled():
            return

        _run_refresh("scheduled")


def check_on_demand_refresh_job():
    if _app is None:
        return

    with _app.app_context():
        from src.app.services import settings_service

        if settings_service.get_setting("refresh_requested") != "1":
            return

        last_at = settings_service.get_setting("last_on_demand_refresh_at")
        if last_at:
            try:
                last_time = datetime.fromisoformat(last_at)
                if datetime.now(timezone.utc) - last_time < timedelta(minutes=ON_DEMAND_COOLDOWN_MINUTES):
                    settings_service.set_setting("refresh_requested", "0")
                    return
            except ValueError:
                pass

        settings_service.set_setting("refresh_requested", "0")
        settings_service.set_setting(
            "last_on_demand_refresh_at",
            datetime.now(timezone.utc).isoformat()
        )
        _run_refresh("on-demand")


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

    scheduler.add_job(
        check_on_demand_refresh_job,
        trigger=IntervalTrigger(seconds=ON_DEMAND_POLL_SECONDS),
        id="check_on_demand_refresh",
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
