"""Fixtures partagées pour la suite pytest de smoke tests.

L'objectif de ces tests est de fournir un filet de sécurité minimal AVANT
le refactor structurel : ils n'épuisent pas la spec mais s'assurent que les
parcours critiques (login, création de session, dashboard, admin) restent
fonctionnels après chaque étape d'extraction.
"""

import os
import tempfile
from pathlib import Path

import pytest

# Le module app.config évalue `Config` à l'import (mkdir de DATA_DIR, fallback
# SECRET_KEY/FERNET_KEY selon FLASK_ENV, etc.). Il faut donc poser ces
# variables d'environnement AVANT d'importer quoi que ce soit de `app`.
_TMP_DATA_DIR = Path(tempfile.mkdtemp(prefix="english_explorer_tests_"))
os.environ.setdefault("FLASK_ENV", "development")
os.environ.setdefault("DATA_DIR", str(_TMP_DATA_DIR))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP_DATA_DIR}/test.db")
os.environ.setdefault("DEFAULT_ADMIN_EMAIL", "admin@test.local")
os.environ.setdefault("DEFAULT_ADMIN_PASSWORD", "AdminTest1234!")

from app import create_app, db, limiter  # noqa: E402
from app.models import Student  # noqa: E402

# Le rate-limiter sur /login (10/min) ferait sauter les tests qui enchaînent
# plus de 10 logins dans la même minute. On le désactive en amont.
limiter.enabled = False


TEST_PASSWORD = "TestPass1234!"


@pytest.fixture(scope="session")
def app():
    application = create_app()
    application.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        RATELIMIT_ENABLED=False,
        SERVER_NAME="localhost.localdomain",
    )
    return application


@pytest.fixture(autouse=True)
def _reset_db(app):
    """Vide les tables non-référentielles entre tests pour l'isolation.

    On garde les seeds (catégories, badges, prérequis, prompts, admin) qui
    sont posés par `create_app()` au démarrage — les recréer à chaque test
    coûterait cher et n'apporte rien au filet de sécurité.
    """
    with app.app_context():
        # On purge uniquement ce qui peut diverger entre tests.
        from app.models import (
            SessionExercise,
            PracticeSession,
            PreparedExerciseQuestion,
            PreparedExerciseSet,
            PreparedExercise,
            StudentBadge,
            StudentSkillProgress,
            ReviewPlan,
            WeeklyGoal,
            AICallLog,
            AIGeneratedExercise,
            SessionTranslationLog,
        )

        for model in (
            SessionExercise,
            PracticeSession,
            PreparedExerciseQuestion,
            PreparedExerciseSet,
            PreparedExercise,
            StudentBadge,
            StudentSkillProgress,
            ReviewPlan,
            WeeklyGoal,
            AICallLog,
            AIGeneratedExercise,
            SessionTranslationLog,
        ):
            db.session.query(model).delete()

        # La table d'association parent_student référence students.id : on la
        # purge avant la suppression des Student pour éviter une FK violation.
        from app.models import parent_student

        db.session.execute(parent_student.delete())
        Student.query.filter(Student.role != "admin").delete()
        db.session.commit()
    yield


@pytest.fixture
def client(app):
    return app.test_client()


def _create_user(role: str, email: str, first_name: str = "Test") -> Student:
    user = Student(first_name=first_name, email=email, role=role)
    user.set_password(TEST_PASSWORD)
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def parent_user(app):
    with app.app_context():
        user = _create_user("parent", "parent@test.local", "Parent")
        return {"id": user.id, "email": user.email, "password": TEST_PASSWORD}


@pytest.fixture
def student_user(app):
    with app.app_context():
        user = _create_user("student", "kid@test.local", "Kid")
        return {"id": user.id, "email": user.email, "password": TEST_PASSWORD}


@pytest.fixture
def admin_user(app):
    # L'admin est seedé par `ensure_admin_account()` dans `create_app()`.
    return {
        "email": os.environ["DEFAULT_ADMIN_EMAIL"],
        "password": os.environ["DEFAULT_ADMIN_PASSWORD"],
    }


def _login(client, email: str, password: str):
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )


@pytest.fixture
def login(client):
    """Helper de login renvoyant le statut + permet de chaîner."""

    def _do(email: str, password: str):
        return _login(client, email, password)

    return _do
