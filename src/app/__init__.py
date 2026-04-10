import atexit
import logging
import os
import sys

from flask import Flask
from src.app.database import init_db


def _configure_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def create_app(config: dict | None = None) -> Flask:
    _configure_logging()

    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static"
    )

    app.config["DATABASE"] = os.environ.get("DATABASE_PATH", "myfeeds.db")
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    app.config["SCHEDULER_ENABLED"] = os.environ.get("SCHEDULER_ENABLED", "true").lower() == "true"

    if config:
        app.config.update(config)

    init_db(app)

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "img-src 'self' https: data:; "
            "style-src 'self' 'unsafe-inline'"
        )
        return response

    from src.app import routes
    app.register_blueprint(routes.bp)

    if app.config.get("SCHEDULER_ENABLED") and not app.config.get("TESTING"):
        from src.app.scheduler import init_scheduler, shutdown_scheduler
        init_scheduler(app)
        atexit.register(shutdown_scheduler)

    return app
