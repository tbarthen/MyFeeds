import atexit
import os

from flask import Flask
from src.app.database import init_db


def create_app(config: dict | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static"
    )

    app.config["DATABASE"] = os.environ.get("DATABASE_PATH", "myfeeds.db")
    app.config["SECRET_KEY"] = "dev-secret-key-change-in-production"
    app.config["SCHEDULER_ENABLED"] = True

    if config:
        app.config.update(config)

    init_db(app)

    from src.app import routes
    app.register_blueprint(routes.bp)

    if app.config.get("SCHEDULER_ENABLED") and not app.config.get("TESTING"):
        from src.app.scheduler import init_scheduler, shutdown_scheduler
        init_scheduler(app)
        atexit.register(shutdown_scheduler)

    return app
