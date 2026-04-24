from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import src.app.scheduler as scheduler_module
from src.app.services import settings_service


def _set_app(app):
    scheduler_module._app = app


def _clear_app():
    scheduler_module._app = None


def test_on_demand_refresh_noop_without_app():
    _clear_app()
    with patch("src.app.services.feed_service.refresh_all_feeds") as mock_refresh:
        scheduler_module.check_on_demand_refresh_job()
        mock_refresh.assert_not_called()


def test_on_demand_refresh_noop_when_not_requested(app):
    _set_app(app)
    try:
        with patch("src.app.services.feed_service.refresh_all_feeds") as mock_refresh:
            scheduler_module.check_on_demand_refresh_job()
            mock_refresh.assert_not_called()
    finally:
        _clear_app()


def test_on_demand_refresh_runs_when_requested(app):
    _set_app(app)
    try:
        with app.app_context():
            settings_service.set_setting("refresh_requested", "1")

        with patch("src.app.services.feed_service.refresh_all_feeds", return_value={}) as mock_refresh:
            scheduler_module.check_on_demand_refresh_job()
            mock_refresh.assert_called_once()

        with app.app_context():
            assert settings_service.get_setting("refresh_requested") == "0"
            assert settings_service.get_setting("last_on_demand_refresh_at") is not None
    finally:
        _clear_app()


def test_on_demand_refresh_debounced_within_cooldown(app):
    _set_app(app)
    try:
        recent = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        with app.app_context():
            settings_service.set_setting("refresh_requested", "1")
            settings_service.set_setting("last_on_demand_refresh_at", recent)

        with patch("src.app.services.feed_service.refresh_all_feeds") as mock_refresh:
            scheduler_module.check_on_demand_refresh_job()
            mock_refresh.assert_not_called()

        with app.app_context():
            assert settings_service.get_setting("refresh_requested") == "0"
    finally:
        _clear_app()


def test_on_demand_refresh_runs_after_cooldown_expires(app):
    _set_app(app)
    try:
        stale = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        with app.app_context():
            settings_service.set_setting("refresh_requested", "1")
            settings_service.set_setting("last_on_demand_refresh_at", stale)

        with patch("src.app.services.feed_service.refresh_all_feeds", return_value={}) as mock_refresh:
            scheduler_module.check_on_demand_refresh_job()
            mock_refresh.assert_called_once()
    finally:
        _clear_app()
