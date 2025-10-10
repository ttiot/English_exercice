# config.py
import os
from datetime import timedelta
from pathlib import Path


class Config:
    # --- Sécurité ---
    FLASK_ENV = os.environ.get("FLASK_ENV", "production")
    SECRET_KEY = os.environ.get("SECRET_KEY")
    if not SECRET_KEY:
        if FLASK_ENV == "development":
            SECRET_KEY = "dev-secret-key-for-development-only"
        else:
            raise ValueError("SECRET_KEY doit être défini en production")

    # --- Dossiers ---
    # Dans un conteneur, on stocke la DB et les uploads dans /data (volume)
    DATA_DIR = Path(os.environ.get("DATA_DIR", "/data")).resolve()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # DB: sqlite absolu => 4 slashes après sqlite:
    DEFAULT_SQLITE_PATH = DATA_DIR / "app.db"
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DATABASE_URL") or f"sqlite:///{DEFAULT_SQLITE_PATH}"
    )

    # SQLAlchemy
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Pour SQLite, il faut souvent lever les verrous de thread et activer WAL
    # On passe par ENGINE_OPTIONS pour configurer le connect
    SQLALCHEMY_ENGINE_OPTIONS = {
        # Evite les connexions mortes dans le pool
        "pool_pre_ping": True,
        # Paramètres spécifiques SQLite
        "connect_args": {
            # On laisse SQLAlchemy gérer la concurrence, pas la contrainte du thread unique
            "check_same_thread": False,
        },
    }

    # Cookies de session
    SESSION_COOKIE_SECURE = FLASK_ENV != "development"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    REMEMBER_COOKIE_DURATION = timedelta(days=30)

    # Admin bootstrap (toujours par env en prod)
    DEFAULT_ADMIN_EMAIL = os.environ.get("DEFAULT_ADMIN_EMAIL", "admin@example.com")
    DEFAULT_ADMIN_PASSWORD = os.environ.get("DEFAULT_ADMIN_PASSWORD")
    if not DEFAULT_ADMIN_PASSWORD:
        if FLASK_ENV == "development":
            DEFAULT_ADMIN_PASSWORD = "admin1234"
        else:
            raise ValueError("DEFAULT_ADMIN_PASSWORD doit être défini en production")

    # Uploads => /data/uploads (volume)
    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER", str((DATA_DIR / "uploads").resolve())
    )
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
