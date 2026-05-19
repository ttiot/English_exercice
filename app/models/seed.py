"""Insertion idempotente des données de référence (catégories, badges,
prérequis, prompts IA, compte admin de bootstrap).

Toutes ces fonctions sont appelées au démarrage par ``create_app()``.
"""

from sqlalchemy.exc import IntegrityError

from ..extensions import db
from .ai import OpenAIPrompt
from .categories import (
    DEFAULT_CATEGORY_METADATA,
    DEFAULT_CATEGORY_NAMES,
    QuestionCategory,
    SkillPrerequisite,
)
from .core import Student
from .progression import Badge


def ensure_default_badges() -> None:
    existing = {badge.code: badge for badge in Badge.query.all()}
    categories = {category.code: category for category in QuestionCategory.query.all()}
    created = False

    for code, label in DEFAULT_CATEGORY_NAMES:
        category = categories.get(code)
        if not category:
            continue
        badge_code = f"{code}_mastery"
        badge = existing.get(badge_code)
        if not badge:
            badge = Badge(
                code=badge_code,
                name=f"Maîtrise {label}",
                description=f"Atteindre 80% de réussite sur {label}.",
                category=category,
                min_mastery=80.0,
                min_streak=2,
            )
            db.session.add(badge)
            created = True
        else:
            badge.category = category
            badge.min_mastery = 80.0
            badge.min_streak = 2
            created = True

    if created:
        db.session.commit()


def ensure_default_categories() -> None:
    existing = {
        category.code: category for category in QuestionCategory.query.all()
    }
    created = False

    for code, name in DEFAULT_CATEGORY_NAMES:
        category = existing.get(code)
        if not category:
            category = QuestionCategory(code=code, name=name)
            db.session.add(category)
            created = True
        elif category.name != name:
            category.name = name
            created = True
        metadata = DEFAULT_CATEGORY_METADATA.get(code)
        if metadata:
            category.domain = metadata.get("domain")
            category.cecrl_level = metadata.get("cecrl_level")
            category.grade_level = metadata.get("grade_level")
            category.trimester = metadata.get("trimester")
            category.order_index = metadata.get("order_index")
            category.unlocked_by_default = bool(metadata.get("unlocked_by_default", True))
            created = True

    if created:
        db.session.commit()


def ensure_default_prompts() -> None:
    """Crée la ligne ``OpenAIPrompt`` pour chaque clé connue dans
    ``_DEFAULT_PROMPTS``. Idempotent : ne touche pas aux lignes existantes
    (un admin peut avoir édité le contenu)."""
    from ..services.ai_generator import _DEFAULT_PROMPTS

    _OUTDATED_SENTINELS = {
        "generate_exercises": "sauf pour une demande explicite de traduction de l'anglais vers le français",
    }

    existing_keys = {p.prompt_key for p in OpenAIPrompt.query.all()}
    created = False
    for key, defaults in _DEFAULT_PROMPTS.items():
        if key in existing_keys:
            existing = OpenAIPrompt.query.filter_by(prompt_key=key).first()
            sentinel = _OUTDATED_SENTINELS.get(key)
            if existing and sentinel and sentinel in (existing.system_prompt or ""):
                existing.system_prompt = defaults["system_prompt"]
                created = True
            continue
        db.session.add(
            OpenAIPrompt(
                prompt_key=key,
                display_name=defaults["display_name"],
                description=defaults.get("description"),
                system_prompt=defaults["system_prompt"],
                user_prompt_template=defaults["user_prompt_template"],
                available_variables=defaults.get("available_variables"),
                parameters_json=defaults.get("parameters_json"),
                is_active=True,
            )
        )
        created = True
    if created:
        db.session.commit()


def ensure_default_prerequisites() -> None:
    if SkillPrerequisite.query.count() > 0:
        return

    category_lookup = {
        category.code: category for category in QuestionCategory.query.all()
    }

    rules = [
        ("sentence_en_fr", "translate_en_fr", 60.0),
        ("sentence_fr_en", "translate_fr_en", 60.0),
        ("daily_routine", "school_vocab", 55.0),
        ("hobbies_vocab", "family_vocab", 55.0),
        ("adjectives_opposites", "grammar_pronouns", 55.0),
        ("culture_countries", "sentence_en_fr", 60.0),
    ]

    for category_code, prerequisite_code, min_mastery in rules:
        category = category_lookup.get(category_code)
        prerequisite = category_lookup.get(prerequisite_code)
        if not category or not prerequisite:
            continue
        db.session.add(
            SkillPrerequisite(
                category_id=category.id,
                prerequisite_id=prerequisite.id,
                min_mastery=min_mastery,
            )
        )

    db.session.commit()


def ensure_admin_account(default_email: str, default_password: str) -> None:
    if not default_email or not default_password:
        return

    existing_admin = Student.query.filter_by(role="admin").first()
    if existing_admin:
        return

    existing_email = Student.query.filter_by(email=default_email).first()
    if existing_email:
        # Ne pas écraser un compte existant (évite l'erreur d'unicité)
        return

    admin = Student(
        first_name="Admin",
        last_name=None,
        email=default_email,
        role="admin",
    )
    admin.set_password(default_password)
    db.session.add(admin)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
