from src.app.database import get_db


DEFAULT_SETTINGS = {
    "refresh_interval_minutes": "30",
    "auto_refresh_enabled": "1",
}


def get_setting(key: str) -> str | None:
    db = get_db()
    row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row:
        return row["value"]
    return DEFAULT_SETTINGS.get(key)


def set_setting(key: str, value: str) -> None:
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value)
    )
    db.commit()


def get_all_settings() -> dict[str, str]:
    db = get_db()
    rows = db.execute("SELECT key, value FROM settings").fetchall()
    settings = dict(DEFAULT_SETTINGS)
    for row in rows:
        settings[row["key"]] = row["value"]
    return settings


def get_refresh_interval() -> int:
    value = get_setting("refresh_interval_minutes")
    try:
        return int(value) if value else 30
    except ValueError:
        return 30


def is_auto_refresh_enabled() -> bool:
    value = get_setting("auto_refresh_enabled")
    return value == "1"
