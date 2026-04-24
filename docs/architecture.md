# Architecture

## Runtime topology

Three containers defined in `docker-compose.yml`:

- **myfeeds** — Flask web app served by gunicorn. Handles HTTP only. `SCHEDULER_ENABLED=false`.
- **scheduler** — Same image, runs `src.scheduler_runner`. Owns APScheduler and the feed-refresh job. No HTTP.
- **autoheal** — Restarts containers labeled `autoheal=true` when their healthcheck fails.

Both app containers mount the same `myfeeds-data` Docker volume holding the SQLite database. SQLite WAL mode allows concurrent readers and serializes writers with a 10-second busy timeout.

## Why the scheduler is a separate container

The web and scheduler ran in one container originally, with APScheduler's `BackgroundScheduler` inside the gunicorn worker process. During feed refresh, feedparser's XML parsing is CPU-bound and holds the GIL. The `/health` endpoint shares that process, so healthcheck requests couldn't be serviced within the 5-second timeout. After 3 failed checks, autoheal restarted the container — killing the in-progress refresh mid-flight. This happened multiple times per day.

Splitting the scheduler out means:
- The web container stays idle and responsive during refreshes, so /health always answers fast.
- The scheduler container can peg CPU for as long as it needs without tripping a healthcheck. It has its own liveness probe (a heartbeat file touched every 30 s) that measures process health, not workload load.
- A restart of one container doesn't kill work in the other.

**Do not fold these back together.** If you're tempted to simplify by merging them, re-read this section first.

## On-demand refresh on page open

The scheduled interval alone would mean a user reopening the app has to wait up to the full interval (default 30 min) to see new articles. To bridge that, the frontend fires `POST /api/refresh-if-stale` on page load; the web route writes `refresh_requested=1` to the `settings` table and returns immediately. The scheduler container polls that flag every 30 s (`check_on_demand_refresh_job`). When set, and if the last on-demand refresh was more than 5 min ago, it clears the flag and runs the same `refresh_all_feeds` path the interval job uses.

Refresh work stays in the scheduler container so the web container keeps answering `/health` — the reason for the container split still holds.

## Logging

`src/app/__init__.py::_configure_logging` attaches a stdout StreamHandler to the root logger at INFO level. This ensures `logger.info(...)` calls from anywhere in the app (notably `src.app.scheduler`) reach `docker logs`. Gunicorn's own access/error logs are separate.

## Database concurrency

Both containers call `init_db` on startup, which runs idempotent migrations via `_add_column_if_missing`. Races are tolerated — the second process catches `OperationalError` on duplicate ALTER TABLE.

WAL mode is set in both `init_db` (Flask request path) and `get_db_connection` (standalone context manager for scripts).
