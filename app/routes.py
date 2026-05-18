"""Utilitaires partagés par les blueprints.

Après le refactor par étapes, ce module ne contient plus aucune route : tout
a été déplacé dans ``app/blueprints/``. Il reste uniquement quatre helpers
historiques utilisés par plusieurs blueprints via des imports paresseux :

- :func:`_csv_safe` : préfixe d'une cellule CSV pour bloquer l'injection
  de formules dans Excel/LibreOffice ;
- :func:`validate_image_file` : validation stricte d'un upload d'avatar
  (extension + MIME via libmagic + sanity check PIL) ;
- :func:`_slugify_label` : génération d'un code de catégorie depuis un
  label utilisateur ;
- :func:`_delete_avatar_file` : suppression best-effort d'un fichier
  d'avatar dans ``UPLOAD_FOLDER``.

Et quelques constantes d'affichage (``DIFFICULTY_DISPLAY``,
``SESSION_TYPE_LABELS``, ``CEFR_LEVELS``, etc.) référencées par plusieurs
blueprints via ``from ...routes import …``. Si tu cherches une route, elle
est dans ``app/blueprints/<domaine>/``.
"""

from pathlib import Path
from typing import Optional
from uuid import uuid4

from flask import current_app
from werkzeug.utils import secure_filename

try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from .exercise_factory import DIFFICULTY_LABELS, DIFFICULTY_LEVELS


DIFFICULTY_DISPLAY = {**DIFFICULTY_LABELS, "prepared": "Parcours préparé"}
DIFFICULTY_CHOICES = [(value, DIFFICULTY_LABELS[value]) for value in DIFFICULTY_LEVELS]
CEFR_LEVELS = ["A1", "A2"]
GRADE_LEVELS = ["6e", "5e"]
TRIMESTER_CHOICES = [1, 2, 3]
SESSION_TYPE_LABELS = {
    "practice": "Entraînement",
    "challenge": "Défi",
    "control": "Contrôle",
    "prepared": "Parcours préparé",
    "ai_custom": "Prompt libre (IA)",
}


def _csv_safe(value) -> str:
    """Préfixe les cellules CSV commençant par un caractère de formule (=, +, -, @, |, %)
    pour prévenir l'injection de formules dans Excel / LibreOffice."""
    s = str(value) if value is not None else ""
    if s and s[0] in ('=', '+', '-', '@', '|', '%'):
        return "'" + s
    return s


def validate_image_file(file):
    """Validation stricte des fichiers image."""
    if not file or not file.filename:
        return False

    sanitized = secure_filename(file.filename)
    extension = sanitized.rsplit(".", 1)[-1].lower() if "." in sanitized else ""
    if extension not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
        return False

    if MAGIC_AVAILABLE:
        file_type = magic.from_buffer(file.read(1024), mime=True)
        file.seek(0)
        if file_type not in ['image/jpeg', 'image/png', 'image/gif']:
            return False

    if PIL_AVAILABLE:
        try:
            Image.open(file).verify()
            file.seek(0)
            return True
        except Exception:
            return False

    return True


def _slugify_label(label: str) -> str:
    slug = secure_filename(label.lower())
    return slug.replace("-", "_") or f"category_{uuid4().hex[:6]}"


def _delete_avatar_file(filename: Optional[str]) -> None:
    if not filename:
        return
    upload_folder = Path(current_app.config["UPLOAD_FOLDER"])
    candidate = upload_folder / filename
    if candidate.exists():
        try:
            candidate.unlink()
        except OSError:
            current_app.logger.warning("Impossible de supprimer l'ancien avatar %s", candidate)
