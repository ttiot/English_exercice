"""Blueprint ``parents`` : panneau parental (dashboard, gestion catégories,
édition de sessions, exercices préparés, génération IA).

Le blueprint est unique mais ses 19 routes sont éclatées en sous-modules
pour rester navigables. Pattern identique à ``app/blueprints/admin/``.

Sous-modules :
- ``dashboard.py``       : ``/dashboard``, ``/weekly-goal``, ``/report``
- ``prepared.py``        : ``/prepared-exercises/new``, ``/import``
- ``categories.py``      : ``/categories/*`` (CRUD)
- ``sessions_edit.py``   : ``/sessions/<id>/*`` (delete, toggle, edit)
- ``ai_gen.py``          : ``/students/<id>/generate-ai-exercises``
- ``exercises_mgmt.py``  : ``/exercises*`` (liste, édition unitaire, bulk)

Préfixe d'URL : ``/parents``.
"""

from flask import Blueprint


bp = Blueprint("parents", __name__, url_prefix="/parents")


# --- Helpers paresseux partagés entre sous-modules ----------------------
# Les helpers d'app/routes.py et des services sont importés à la volée
# (et non au top-level) pour éviter d'alourdir l'arbre d'imports au démarrage
# et préserver l'historique de l'app (où ces helpers vivaient déjà dans
# routes.py avant le refactor).


def _slugify_label(label):
    from ...routes import _slugify_label as impl

    return impl(label)


def _csv_safe(value):
    from ...routes import _csv_safe as impl

    return impl(value)


def _display_constants():
    """Retourne ``(DIFFICULTY_CHOICES, DIFFICULTY_DISPLAY)`` depuis routes.py.

    Utilisé par les templates de dashboard/AI/exercices pour afficher les
    libellés de difficulté en français.
    """
    from ...routes import DIFFICULTY_CHOICES, DIFFICULTY_DISPLAY

    return DIFFICULTY_CHOICES, DIFFICULTY_DISPLAY


def _parse_import_rows_lazy(content, fmt, delim):
    from ...services.imports import _parse_import_rows

    return _parse_import_rows(content, fmt, delim)


def _preserve_filters(source) -> dict:
    """Extrait les paramètres de filtre de l'écran ``/parents/exercises``.

    Sert à les réinjecter dans un ``url_for`` après une action POST (bulk
    edit, batch edit) pour ne pas perdre le contexte de filtrage de
    l'utilisateur lors du redirect.
    """
    keys = ("type", "q", "domain", "difficulty", "student_id", "date_from", "date_to")
    return {k: source.get(k) for k in keys if source.get(k)}


# --- Enregistrement des routes -----------------------------------------
# L'import des sous-modules a pour effet de bord d'enregistrer leurs
# @bp.route(...) sur ``bp``. À placer après la création de ``bp`` et des
# helpers communs pour éviter une circularité.

from . import (  # noqa: E402,F401
    ai_gen,
    categories,
    dashboard,
    exercises_mgmt,
    prepared,
    sessions_edit,
)
