"""Helpers d'authentification et d'autorisation.

Ces fonctions encapsulent l'accès à ``flask.session`` et ``flask.g`` et sont
volontairement les SEULES à manipuler ces objets côté serveur — toutes les
autres couches (services métier, blueprints) reçoivent l'utilisateur courant
en argument explicite.

Les trois décorateurs (``_login_required``, ``_parent_required``,
``_admin_required``) gardent leur préfixe ``_`` pour rester compatibles avec
les usages existants dans ``routes.py``.
"""

from functools import wraps
from typing import Optional
from urllib.parse import urljoin, urlparse

from flask import abort, flash, g, redirect, request, session, url_for

from ..models import Student


def is_safe_url(target: str) -> bool:
    """Vérifie qu'une URL de redirection est same-origin (prévention open redirect)."""
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc


def _load_user_from_session() -> Optional[Student]:
    user_id = session.get("user_id")
    if not user_id:
        return None
    return Student.query.get(user_id)


def _current_user() -> Optional[Student]:
    if not hasattr(g, "current_user"):
        g.current_user = _load_user_from_session()
    return g.current_user


def _login_user(user: Student) -> None:
    session["user_id"] = user.id
    session.permanent = True
    g.current_user = user


def _logout_user() -> None:
    session.pop("user_id", None)
    g.current_user = None


def _get_student_or_404(student_id: int) -> Student:
    student = Student.query.get(student_id)
    if not student:
        abort(404)
    return student


def _get_visible_students(user: Student) -> list:
    if user.is_admin():
        return Student.query.filter_by(role="student").order_by(Student.first_name).all()
    return sorted(user.managed_students, key=lambda s: s.first_name)


def _assert_student_access(user: Student, student: Student) -> None:
    if user.is_admin():
        return
    if student not in user.managed_students:
        abort(403)


def _login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        user = _current_user()
        if not user:
            next_url = request.url if request.method == "GET" else url_for("main.index")
            return redirect(url_for("main.login", next=next_url))
        return view(*args, **kwargs)

    return wrapped_view


def _parent_required(view):
    @wraps(view)
    @_login_required
    def wrapped_view(*args, **kwargs):
        user = _current_user()
        if not user or not (user.is_parent() or user.is_admin()):
            flash("Accès réservé aux parents ou à l'administrateur.", "warning")
            return redirect(url_for("main.index"))
        return view(*args, **kwargs)

    return wrapped_view


def _admin_required(view):
    @wraps(view)
    @_login_required
    def wrapped_view(*args, **kwargs):
        user = _current_user()
        if not user or not user.is_admin():
            flash("Seul l'administrateur peut effectuer cette action.", "warning")
            return redirect(url_for("main.index"))
        return view(*args, **kwargs)

    return wrapped_view


def require_login() -> Optional[None]:
    """Implémentation du ``before_app_request`` global de l'app.

    Bloque tout accès non-authentifié à une route métier en redirigeant
    vers ``/login`` ; laisse passer login/register/logout et les fichiers
    statiques pour éviter les boucles.
    """
    endpoint = request.endpoint or ""
    if endpoint in {"main.login", "main.register", "main.logout"}:
        return None
    if endpoint.startswith("static"):
        return None

    user = _current_user()
    if not user:
        next_url = request.url if request.method == "GET" else url_for("main.index")
        return redirect(url_for("main.login", next=next_url))
    return None
