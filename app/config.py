import os
from datetime import timedelta
from pathlib import Path


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")

    _base_dir = Path(__file__).resolve().parent
    _default_db = _base_dir.parent / "instance" / "app.db"
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or f"sqlite:///{_default_db}"

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    PARENT_PORTAL_PASSWORD = os.environ.get("PARENT_PORTAL_PASSWORD", "parents123")
