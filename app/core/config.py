from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


APP_NAME = "FABOuanes"
BASE_DIR = Path(__file__).resolve().parents[2]


def _default_data_dir() -> Path:
    explicit = os.getenv("FAB_DATA_DIR", "").strip()
    if explicit:
        return Path(explicit)
    local = os.getenv("LOCALAPPDATA", "").strip()
    if local:
        return Path(local) / APP_NAME
    if os.name == "nt":
        return Path.home() / "AppData" / "Local" / APP_NAME
    xdg = os.getenv("XDG_DATA_HOME", "").strip()
    if xdg:
        return Path(xdg) / APP_NAME
    return BASE_DIR / APP_NAME


APP_DATA_DIR = _default_data_dir()
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
BUNDLED_DB_PATH = BASE_DIR / "database.db"

load_dotenv(BASE_DIR / ".env")
if os.getenv("FAB_DESKTOP", "0") == "1":
    load_dotenv(APP_DATA_DIR / ".env", override=False)


@dataclass(slots=True)
class Settings:
    app_name: str = APP_NAME
    base_dir: Path = BASE_DIR
    app_data_dir: Path = APP_DATA_DIR
    env: str = os.getenv("FASTAPI_ENV", os.getenv("FLASK_ENV", "production")).lower()
    desktop_mode: bool = os.getenv("FAB_DESKTOP", "0") == "1"
    secret_key: str = os.getenv("SECRET_KEY", "").strip()
    session_cookie_secure: bool = os.getenv("SESSION_COOKIE_SECURE", "0") == "1"
    default_admin_username: str = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
    default_admin_password: str = os.getenv("DEFAULT_ADMIN_PASSWORD", "")
    host: str = os.getenv("FAB_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port: int = int(os.getenv("FAB_PORT", "5000") or "5000")
    session_max_age: int = int(os.getenv("SESSION_MAX_AGE", str(60 * 60 * 12)))

    @property
    def database_url(self) -> str:
        """Use local SQLite when DATABASE_URL is empty; use PostgreSQL when it is set."""
        configured = os.getenv("DATABASE_URL", "").strip()
        if configured:
            return configured
        db_path = self.app_data_dir / "database.db"
        return f"sqlite:///{db_path}"

    @property
    def debug(self) -> bool:
        return self.env == "development"


settings = Settings()

DATABASE_URL = "" if os.getenv("FAB_DESKTOP", "0").strip() == "1" else os.getenv("DATABASE_URL", "").strip()
SESSION_COOKIE_SECURE = settings.session_cookie_secure
DEFAULT_ADMIN_USERNAME = settings.default_admin_username
DEFAULT_ADMIN_PASSWORD = settings.default_admin_password
ENV = settings.env
DEBUG = settings.debug
