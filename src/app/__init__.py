import atexit
import logging
import os
import sys
from datetime import timedelta

from flask import Flask, redirect, request, session, url_for
from werkzeug.exceptions import HTTPException
from src.app.database import init_db


AUTH_EXEMPT_PREFIXES = ("/login", "/health", "/static/")
WEAK_SECRET_KEYS = {
    "dev-secret-key-change-in-production",
    "change-me-in-production",
    "change-me",
    "not-needed-for-scheduler",
}


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
    app.config["APP_PASSWORD"] = os.environ.get("APP_PASSWORD")
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=365)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    if config:
        app.config.update(config)

    if app.config.get("APP_PASSWORD") and app.config["SECRET_KEY"] in WEAK_SECRET_KEYS:
        logging.getLogger(__name__).critical(
            "APP_PASSWORD is set but SECRET_KEY is a known default; "
            "session cookies are forgeable. Set a strong, unique SECRET_KEY."
        )

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

    @app.before_request
    def require_login():
        if not app.config.get("APP_PASSWORD"):
            return None
        if request.path.startswith(AUTH_EXEMPT_PREFIXES):
            return None
        if session.get("authenticated"):
            return None
        try:
            app.url_map.bind("").match(request.path, method=request.method)
        except HTTPException:
            return None
        return redirect(url_for("main.login", next=request.path))

    from src.app import routes
    app.register_blueprint(routes.bp)

    if app.config.get("SCHEDULER_ENABLED") and not app.config.get("TESTING"):
        from src.app.scheduler import init_scheduler, shutdown_scheduler
        init_scheduler(app)
        atexit.register(shutdown_scheduler)

    return app
