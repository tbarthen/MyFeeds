import pytest

from src.app.services import settings_service


class TestSettings:
    def test_get_default_setting(self, app):
        with app.app_context():
            value = settings_service.get_setting("refresh_interval_minutes")
            assert value == "30"

    def test_set_and_get_setting(self, app):
        with app.app_context():
            settings_service.set_setting("refresh_interval_minutes", "60")
            value = settings_service.get_setting("refresh_interval_minutes")
            assert value == "60"

    def test_get_all_settings(self, app):
        with app.app_context():
            settings = settings_service.get_all_settings()
            assert "refresh_interval_minutes" in settings
            assert "auto_refresh_enabled" in settings

    def test_get_refresh_interval(self, app):
        with app.app_context():
            interval = settings_service.get_refresh_interval()
            assert interval == 30

            settings_service.set_setting("refresh_interval_minutes", "45")
            interval = settings_service.get_refresh_interval()
            assert interval == 45

    def test_get_refresh_interval_invalid(self, app):
        with app.app_context():
            settings_service.set_setting("refresh_interval_minutes", "invalid")
            interval = settings_service.get_refresh_interval()
            assert interval == 30

    def test_is_auto_refresh_enabled(self, app):
        with app.app_context():
            assert settings_service.is_auto_refresh_enabled() is True

            settings_service.set_setting("auto_refresh_enabled", "0")
            assert settings_service.is_auto_refresh_enabled() is False

            settings_service.set_setting("auto_refresh_enabled", "1")
            assert settings_service.is_auto_refresh_enabled() is True
