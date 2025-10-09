import os
from datetime import timedelta


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(os.getcwd(), 'instance', 'app.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    PARENT_PORTAL_PASSWORD = os.environ.get("PARENT_PORTAL_PASSWORD", "parents123")
