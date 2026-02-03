from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

scheduler = BackgroundScheduler()
_app = None


def refresh_all_feeds_job():
    if _app is None:
        return

    with _app.app_context():
        from src.app.services import feed_service, settings_service

        if not settings_service.is_auto_refresh_enabled():
            return

        feed_service.refresh_all_feeds()


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
