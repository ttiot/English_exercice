from datetime import datetime

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf import CSRFProtect
from pathlib import Path

from .config import Config
from flask_wtf.csrf import generate_csrf

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()


def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(Config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    from . import models  # noqa: F401
    from .routes import bp as main_bp

    app.register_blueprint(main_bp)

    with app.app_context():
        db.create_all()

    @app.context_processor
    def inject_globals():
        return {
            "current_year": datetime.utcnow().year,
            "csrf_token": generate_csrf,
        }

    @app.after_request
    def set_csrf_cookie(response):
        response.set_cookie("csrf_token", generate_csrf())
        return response

    return app
