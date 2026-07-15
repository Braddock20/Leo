"""Configuration loader. Reads from .env or environment."""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(val: str | None, default: bool = False) -> bool:
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _int(val: str | None, default: int) -> int:
    try:
        return int(val) if val is not None else default
    except (TypeError, ValueError):
        return default


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-insecure-change-me")
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
    HEADLESS = _bool(os.environ.get("HEADLESS"), True)

    DATA_DIR = BASE_DIR / "data"
    INSTANCE_DIR = BASE_DIR / "instance"
    LOG_DIR = BASE_DIR / "logs"
    for d in (DATA_DIR, INSTANCE_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)

    DB_PATH = INSTANCE_DIR / "igpilot.db"
    FERNET_KEY_PATH = DATA_DIR / ".fernet_key"
    CHROMIUM_PROFILE_DIR = DATA_DIR / "chromium_profile"
    SESSION_LOG_PATH = LOG_DIR / "session.log"

    DAILY_LIKE_LIMIT = _int(os.environ.get("DAILY_LIKE_LIMIT"), 80)
    DAILY_FOLLOW_LIMIT = _int(os.environ.get("DAILY_FOLLOW_LIMIT"), 40)
    DAILY_DM_LIMIT = _int(os.environ.get("DAILY_DM_LIMIT"), 20)
    DAILY_STORY_VIEW_LIMIT = _int(os.environ.get("DAILY_STORY_VIEW_LIMIT"), 100)

    USER_AGENT = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
