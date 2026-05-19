"""Enregistrement centralisé des blueprints de l'application.

Au fur et à mesure que les routes sont éclatées hors de ``app/routes.py``,
on les enregistre ici depuis ``create_app()`` via ``register_blueprints``.
"""

from flask import Flask


def register_blueprints(app: Flask) -> None:
    from .admin import bp as admin_bp
    from .api import bp as api_bp
    from .auth import bp as auth_bp
    from .exercise_bank import bp as exercise_bank_bp
    from .parents import bp as parents_bp
    from .sessions import bp as sessions_bp
    from .students import bp as students_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(students_bp)
    app.register_blueprint(sessions_bp)
    app.register_blueprint(exercise_bank_bp)
    app.register_blueprint(parents_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
