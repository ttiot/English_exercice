"""Factorisation de la validation + persistance des formulaires utilisateur.

Avant ce service, la validation + création/édition d'un ``Student`` était
copiée-collée à 5 endroits :
- ``blueprints/auth.register``           — auto-inscription élève (role figé)
- ``blueprints/students.create_student`` — parent crée un élève
- ``blueprints/students.manage_student`` — édition profil + password
- ``blueprints/admin/users.admin_create_user`` — admin crée n'importe quel rôle
- ``blueprints/admin/users.admin_edit_user``   — admin édite n'importe quel rôle

Le service expose trois entry points qui couvrent les 5 cas, en laissant le
caller gérer le post-traitement spécifique (login auto, rattachement parent,
redirect/render) :

- :func:`create_user_from_form` — validation + persistance d'un nouveau Student
- :func:`update_user_from_form` — validation + mise à jour d'un Student existant
- :func:`change_user_password`  — changement de password (forme self-service ou admin)

En cas d'erreur de validation, une :class:`UserFormError` est levée. Elle
porte un ``message`` (à flasher) plus le ``form_data`` et ``selected_domains``
prêts à être re-passés au template pour préserver la saisie utilisateur.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional
from uuid import uuid4

from flask import current_app
from werkzeug.datastructures import FileStorage, ImmutableMultiDict
from werkzeug.utils import secure_filename

from ..extensions import db
from ..models import Student
from ..validators import (
    sanitize_text_input,
    validate_age,
    validate_email,
    validate_goals,
    validate_name,
    validate_password,
)
from .curriculum import _parse_domain_list


# Rôles autorisés pour les routes admin (et indirectement le défaut "student"
# pour register/create_student).
ALLOWED_ROLES = {"student", "parent", "admin"}


class UserFormError(Exception):
    """Exception levée par les helpers en cas d'erreur de validation.

    Porte :
    - ``message`` : phrase déjà rédigée en français à passer à ``flash(..., "danger")``
    - ``form_data`` : dict prêt à être re-passé au template pour préserver la saisie
    - ``selected_domains`` : liste pour cocher les domaines préférés à l'écran
    """

    def __init__(
        self,
        message: str,
        *,
        form_data: Optional[dict] = None,
        selected_domains: Optional[List[str]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.form_data = form_data or {}
        self.selected_domains = selected_domains or []


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------


def _validate_image_file_lazy(file) -> bool:
    """Délégué paresseux vers ``app.routes.validate_image_file``.

    L'helper vit encore dans ``routes.py`` pour ne pas dupliquer la logique
    libmagic/PIL. Import paresseux pour éviter tout cycle d'import.
    """
    from ..routes import validate_image_file

    return validate_image_file(file)


def _delete_avatar_file_lazy(filename: Optional[str]) -> None:
    from ..routes import _delete_avatar_file

    _delete_avatar_file(filename)


def _save_avatar(file: FileStorage) -> str:
    """Stocke un fichier d'avatar uploadé dans ``UPLOAD_FOLDER`` ; renvoie son nom."""
    sanitized = secure_filename(file.filename)
    extension = sanitized.rsplit(".", 1)[-1].lower() if "." in sanitized else ""
    new_filename = f"{uuid4().hex}.{extension}"
    destination = Path(current_app.config["UPLOAD_FOLDER"]) / new_filename
    file.save(destination)
    return new_filename


def _build_form_data(form: ImmutableMultiDict, *, include_role: bool) -> dict:
    """Prépare le dict à re-passer au template pour préserver la saisie."""
    data = {
        "first_name": sanitize_text_input(form.get("first_name", "")),
        "last_name": sanitize_text_input(form.get("last_name", "")) or "",
        "email": sanitize_text_input(form.get("email", "")).lower(),
        "age": form.get("age", "").strip(),
        "goals": sanitize_text_input(form.get("goals", "")) or "",
        "target_cefr_level": form.get("target_cefr_level") or "",
        "target_grade": form.get("target_grade") or "",
        "target_trimester": form.get("target_trimester") or "",
        "interests": sanitize_text_input(form.get("interests", "")) or "",
    }
    if include_role:
        data["role"] = form.get("role", "student").strip()
    return data


def _raise_with_form(
    message: str,
    form: ImmutableMultiDict,
    *,
    include_role: bool,
) -> None:
    raise UserFormError(
        message,
        form_data=_build_form_data(form, include_role=include_role),
        selected_domains=form.getlist("preferred_domains"),
    )


def _validate_profile_fields(
    form: ImmutableMultiDict,
    *,
    cefr_levels: Iterable[str],
    grade_levels: Iterable[str],
    trimester_choices: Iterable[int],
    include_role: bool,
    skip_validate_name: bool = False,
) -> dict:
    """Valide les champs partagés et renvoie un dict de valeurs nettoyées.

    Lève UserFormError au premier problème. ``skip_validate_name`` permet
    au cas self-edit (``manage_student``) de ne pas appliquer la regex
    stricte sur le prénom — comportement historique préservé.
    """
    first_name = sanitize_text_input(form.get("first_name", ""))
    last_name = sanitize_text_input(form.get("last_name", "")) or None
    email_raw = sanitize_text_input(form.get("email", "")).lower()
    age_raw = form.get("age", "").strip()
    goals = sanitize_text_input(form.get("goals", "")) or None
    target_cefr_level = form.get("target_cefr_level") or None
    target_grade = form.get("target_grade") or None
    target_trimester_raw = form.get("target_trimester") or ""
    interests = sanitize_text_input(form.get("interests", "")) or None
    preferred_domains = _parse_domain_list(form.getlist("preferred_domains"))

    if skip_validate_name:
        if not first_name:
            _raise_with_form("Le prénom est obligatoire.", form, include_role=include_role)
    else:
        if not validate_name(first_name):
            _raise_with_form(
                "Le prénom contient des caractères invalides ou est trop long.",
                form, include_role=include_role,
            )
        if last_name and not validate_name(last_name):
            _raise_with_form(
                "Le nom de famille contient des caractères invalides ou est trop long.",
                form, include_role=include_role,
            )

    if skip_validate_name:
        if not email_raw:
            _raise_with_form("L'adresse e-mail est obligatoire.", form, include_role=include_role)
    else:
        if not validate_email(email_raw):
            _raise_with_form("L'adresse e-mail n'est pas valide.", form, include_role=include_role)

    if skip_validate_name:
        # self-edit : age = int simple, sans plage
        try:
            age_value = int(age_raw) if age_raw else None
        except ValueError:
            _raise_with_form("L'âge doit être un nombre.", form, include_role=include_role)
    else:
        age_value = validate_age(age_raw)
        if age_raw and age_value is None:
            _raise_with_form(
                "L'âge doit être un nombre valide entre 3 et 120 ans.",
                form, include_role=include_role,
            )

    if goals and not validate_goals(goals):
        _raise_with_form(
            "Les objectifs contiennent du contenu invalide.",
            form, include_role=include_role,
        )

    if target_cefr_level and target_cefr_level not in set(cefr_levels):
        _raise_with_form("Le niveau CECRL est invalide.", form, include_role=include_role)

    if target_grade and target_grade not in set(grade_levels):
        _raise_with_form("Le niveau scolaire est invalide.", form, include_role=include_role)

    target_trimester: Optional[int] = None
    if target_trimester_raw:
        try:
            target_trimester = int(target_trimester_raw)
        except ValueError:
            _raise_with_form("Le trimestre est invalide.", form, include_role=include_role)
        if target_trimester not in set(trimester_choices):
            _raise_with_form("Le trimestre est invalide.", form, include_role=include_role)

    return {
        "first_name": first_name,
        "last_name": last_name,
        "email": email_raw,
        "age": age_value,
        "goals": goals,
        "target_cefr_level": target_cefr_level,
        "target_grade": target_grade,
        "target_trimester": target_trimester,
        "interests": interests,
        "preferred_domains": preferred_domains or None,
    }


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------


def create_user_from_form(
    form: ImmutableMultiDict,
    files: dict,
    *,
    role_choice_allowed: bool,
    default_role: str = "student",
    cefr_levels: Iterable[str] = ("A1", "A2"),
    grade_levels: Iterable[str] = ("6e", "5e"),
    trimester_choices: Iterable[int] = (1, 2, 3),
) -> Student:
    """Valide le form de création + persiste un nouveau Student.

    Le caller est responsable du flash de succès et du redirect.

    Si ``role_choice_allowed`` est vrai, ``form["role"]`` choisit parmi
    ``ALLOWED_ROLES`` ; sinon le rôle est figé à ``default_role``. Quand
    le rôle final n'est pas ``student``, les champs pédagogiques (CEFR,
    grade, trimestre, intérêts, domaines préférés) sont ignorés.
    """
    fields = _validate_profile_fields(
        form,
        cefr_levels=cefr_levels,
        grade_levels=grade_levels,
        trimester_choices=trimester_choices,
        include_role=role_choice_allowed,
    )

    # Résolution du rôle
    if role_choice_allowed:
        role = form.get("role", default_role).strip()
        if role not in ALLOWED_ROLES:
            _raise_with_form("Rôle invalide.", form, include_role=True)
    else:
        role = default_role

    # Si le rôle n'est pas élève, on rend les champs pédagogiques inopérants.
    if role != "student":
        fields["age"] = None
        fields["goals"] = None
        fields["target_cefr_level"] = None
        fields["target_grade"] = None
        fields["target_trimester"] = None
        fields["interests"] = None
        fields["preferred_domains"] = None

    # Mot de passe (obligatoire à la création).
    password = form.get("password", "")
    password_confirm = form.get("password_confirm", "")
    password_valid, password_message = validate_password(password)
    if not password_valid:
        _raise_with_form(password_message, form, include_role=role_choice_allowed)
    if password != password_confirm:
        _raise_with_form(
            "La confirmation du mot de passe ne correspond pas.",
            form, include_role=role_choice_allowed,
        )

    # Email unique
    if Student.query.filter_by(email=fields["email"]).first():
        _raise_with_form(
            "Cette adresse e-mail est déjà utilisée.",
            form, include_role=role_choice_allowed,
        )

    # Avatar (optionnel)
    avatar_filename: Optional[str] = None
    avatar_file = files.get("avatar") if files else None
    if avatar_file and avatar_file.filename:
        if not _validate_image_file_lazy(avatar_file):
            _raise_with_form(
                "Format d'image non pris en charge ou fichier invalide.",
                form, include_role=role_choice_allowed,
            )
        avatar_filename = _save_avatar(avatar_file)

    student = Student(
        first_name=fields["first_name"],
        last_name=fields["last_name"],
        email=fields["email"],
        age=fields["age"],
        goals=fields["goals"],
        target_cefr_level=fields["target_cefr_level"],
        target_grade=fields["target_grade"],
        target_trimester=fields["target_trimester"],
        interests=fields["interests"],
        preferred_domains=fields["preferred_domains"],
        avatar_filename=avatar_filename,
        role=role,
    )
    student.set_password(password)
    db.session.add(student)
    db.session.commit()
    return student


def update_user_from_form(
    target: Student,
    form: ImmutableMultiDict,
    files: dict,
    *,
    role_choice_allowed: bool,
    current_user: Student,
    cefr_levels: Iterable[str] = ("A1", "A2"),
    grade_levels: Iterable[str] = ("6e", "5e"),
    trimester_choices: Iterable[int] = (1, 2, 3),
    skip_validate_name: bool = False,
    accept_inline_password: bool = False,
) -> Student:
    """Valide le form d'édition + met à jour ``target``.

    Si ``role_choice_allowed`` est vrai, ``form["role"]`` peut promouvoir/
    rétrograder le compte cible. Si l'acteur courant essaie de retirer son
    propre rôle admin, une UserFormError est levée.

    ``accept_inline_password`` (admin_edit_user) accepte un champ ``password``
    optionnel directement dans ce form ; sinon le password change passe
    par :func:`change_user_password`.

    ``skip_validate_name`` (manage_student self-edit) applique la
    validation laxiste historique (pas de regex sur first_name, age
    sans plage).
    """
    fields = _validate_profile_fields(
        form,
        cefr_levels=cefr_levels,
        grade_levels=grade_levels,
        trimester_choices=trimester_choices,
        include_role=role_choice_allowed,
        skip_validate_name=skip_validate_name,
    )

    # Résolution du rôle
    if role_choice_allowed:
        role = form.get("role", target.role).strip()
        if role not in ALLOWED_ROLES:
            _raise_with_form("Rôle invalide.", form, include_role=True)
        if current_user.id == target.id and role != "admin":
            _raise_with_form(
                "Vous ne pouvez pas retirer votre propre rôle d'administrateur.",
                form, include_role=True,
            )
    else:
        role = target.role

    if role != "student":
        fields["age"] = None
        fields["goals"] = None
        fields["target_cefr_level"] = None
        fields["target_grade"] = None
        fields["target_trimester"] = None
        fields["interests"] = None
        fields["preferred_domains"] = None

    # Mot de passe inline (admin_edit_user uniquement)
    if accept_inline_password:
        password = form.get("password", "").strip()
        password_confirm = form.get("password_confirm", "").strip()
        if password:
            password_valid, password_message = validate_password(password)
            if not password_valid:
                _raise_with_form(password_message, form, include_role=True)
            if password != password_confirm:
                _raise_with_form(
                    "La confirmation du mot de passe ne correspond pas.",
                    form, include_role=True,
                )
            target.set_password(password)

    # Email unique (en excluant la cible actuelle)
    conflict = Student.query.filter(
        Student.email == fields["email"], Student.id != target.id
    ).first()
    if conflict:
        _raise_with_form(
            "Cette adresse e-mail est déjà utilisée.",
            form, include_role=role_choice_allowed,
        )

    # Avatar : suppression et/ou remplacement
    remove_avatar = form.get("remove_avatar") == "on"
    avatar_file = files.get("avatar") if files else None
    new_avatar_filename: Optional[str] = None
    if avatar_file and avatar_file.filename:
        if not _validate_image_file_lazy(avatar_file):
            _raise_with_form(
                "Format d'image non pris en charge ou fichier invalide.",
                form, include_role=role_choice_allowed,
            )
        new_avatar_filename = _save_avatar(avatar_file)

    if remove_avatar and target.avatar_filename:
        _delete_avatar_file_lazy(target.avatar_filename)
        target.avatar_filename = None

    if new_avatar_filename:
        if target.avatar_filename and target.avatar_filename != new_avatar_filename:
            _delete_avatar_file_lazy(target.avatar_filename)
        target.avatar_filename = new_avatar_filename

    target.first_name = fields["first_name"]
    target.last_name = fields["last_name"]
    target.email = fields["email"]
    target.age = fields["age"]
    target.goals = fields["goals"]
    target.target_cefr_level = fields["target_cefr_level"]
    target.target_grade = fields["target_grade"]
    target.target_trimester = fields["target_trimester"]
    target.interests = fields["interests"]
    target.preferred_domains = fields["preferred_domains"]
    if role_choice_allowed:
        target.role = role

    db.session.commit()
    return target


def change_user_password(
    target: Student,
    form: ImmutableMultiDict,
    *,
    parent_ok: bool,
    min_length: int = 8,
) -> None:
    """Action self-service de changement de mot de passe.

    Comportement préservé tel quel depuis ``students.manage_student`` :
    contrainte de longueur ``min_length`` (par défaut 8), confirmation
    exacte, et l'ancien mot de passe n'est exigé que si l'acteur n'a pas
    le rôle parent/admin (``parent_ok=False``).
    """
    current_password = form.get("current_password", "").strip()
    new_password = form.get("new_password", "").strip()
    confirm_password = form.get("confirm_password", "").strip()

    if len(new_password) < min_length:
        raise UserFormError(
            f"Le nouveau mot de passe doit contenir au moins {min_length} caractères.",
        )
    if new_password != confirm_password:
        raise UserFormError("La confirmation du mot de passe ne correspond pas.")
    if not parent_ok and not target.check_password(current_password):
        raise UserFormError("L'ancien mot de passe est incorrect.")

    target.set_password(new_password)
    db.session.commit()
