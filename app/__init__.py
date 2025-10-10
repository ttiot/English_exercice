from datetime import datetime
from pathlib import Path

from flask import Flask, g
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf import CSRFProtect
from flask_wtf.csrf import generate_csrf
from sqlalchemy import event
from sqlalchemy.engine import Engine

from .config import Config

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()


def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(Config)

    # Dossiers persistant (DB/Uploads), ok pour Docker (/data/…)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    # Importe tes modèles/routes
    from . import models  # noqa: F401
    from .models import (
        Student,
        ensure_default_categories,
        ensure_admin_account,
        ensure_schema_migrations,
    )
    from .routes import bp as main_bp, _load_user_from_session

    app.register_blueprint(main_bp)

    # --- SQLite PRAGMA au connect (WAL, etc.) ---
    @event.listens_for(Engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, conn_record):
        try:
            import sqlite3

            if isinstance(dbapi_conn, sqlite3.Connection):
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL;")
                cur.execute("PRAGMA synchronous=NORMAL;")
                cur.execute("PRAGMA foreign_keys=ON;")
                cur.close()
        except Exception:
            # Ne bloque pas le démarrage si le hook échoue
            pass

    # --- Initialisation base ---
    # En prod, on préfère "flask db upgrade" (Alembic) au lieu de create_all
    with app.app_context():
        if app.config.get("FLASK_ENV") == "development":
            db.create_all()
        ensure_schema_migrations()
        ensure_default_categories()
        ensure_admin_account(Config.DEFAULT_ADMIN_EMAIL, Config.DEFAULT_ADMIN_PASSWORD)

    # --- Healthcheck ---
    @app.get("/health")
    def health():
        return {"status": "ok"}, 200

    # --- User en contexte ---
    @app.before_request
    def load_current_user():
        g.current_user = _load_user_from_session()

    @app.context_processor
    def inject_globals():
        current_user = getattr(g, "current_user", None)
        return {
            "current_year": datetime.utcnow().year,
            "csrf_token": generate_csrf,
            "current_user": current_user,
        }

    # --- Headers de sécurité & (optionnel) cookie CSRF ---
    @app.after_request
    def set_security_headers(response):
        # Headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # X-XSS-Protection est obsolète → inutile en 2025
        # HSTS seulement si HTTPS (et donc cookies Secure)
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # CSP : garde 'unsafe-inline' le temps de nettoyer tes templates/scripts inline
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "script-src 'self' 'unsafe-inline'"
        )

        # Cookie CSRF (OPTIONNEL pour double-submit). Si non nécessaire, commente ce bloc.
        # HttpOnly=False si tu dois lire le token côté client (JS). Sinon, évite ce cookie.
        # response.set_cookie(
        #     "csrf_token",
        #     generate_csrf(),
        #     secure=app.config.get("SESSION_COOKIE_SECURE", True),
        #     httponly=False,
        #     samesite=app.config.get("SESSION_COOKIE_SAMESITE", "Lax"),
        # )
        return response

    return app
