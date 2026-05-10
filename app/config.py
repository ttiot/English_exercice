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

    # Clé Fernet pour chiffrer la clé API OpenAI stockée en BDD.
    # En dev, on auto-génère une clé éphémère (toute clé OpenAI saisie
    # devient illisible au prochain démarrage, ce qui est acceptable en dev).
    FERNET_KEY = os.environ.get("FERNET_KEY")
    if not FERNET_KEY:
        if FLASK_ENV == "development":
            from cryptography.fernet import Fernet

            FERNET_KEY = Fernet.generate_key().decode()
        else:
            raise ValueError("FERNET_KEY doit être défini en production")

    # --- Dossiers ---
    # Dans un conteneur, on stocke la DB et les uploads dans /data (volume)
    DATA_DIR = Path(os.environ.get("DATA_DIR", "/data")).resolve()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # DB: sqlite absolu => 4 slashes après sqlite:
    DEFAULT_SQLITE_PATH = DATA_DIR / "app.db"
    
    # Si DATABASE_URL est fournie, on l'utilise telle quelle
    # Sinon on construit l'URI avec le chemin par défaut
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        SQLALCHEMY_DATABASE_URI = database_url
    else:
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{DEFAULT_SQLITE_PATH}"

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
    SESSION_COOKIE_SAMESITE = "Strict"

    REMEMBER_COOKIE_DURATION = timedelta(days=30)

    # Taille maximale des requêtes (upload + formulaires) : 5 Mo
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024

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

    # OpenAI : valeurs de repli si aucun OpenAIConfig actif en BDD.
    # La page admin /admin/openai/config est la voie nominale.
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
