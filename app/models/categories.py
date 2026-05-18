"""Taxonomie des catégories d'exercices et prérequis pédagogiques."""

from typing import Dict, Sequence

from ..extensions import db
from .core import TimestampMixin


class QuestionCategory(db.Model, TimestampMixin):
    __tablename__ = "question_categories"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(80), nullable=False, unique=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    domain = db.Column(db.String(50), nullable=True)
    cecrl_level = db.Column(db.String(10), nullable=True)
    grade_level = db.Column(db.String(10), nullable=True)
    trimester = db.Column(db.Integer, nullable=True)
    order_index = db.Column(db.Integer, nullable=True)
    unlocked_by_default = db.Column(db.Boolean, default=True, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - repr utility
        return f"<QuestionCategory {self.code}>"


class SkillPrerequisite(db.Model, TimestampMixin):
    __tablename__ = "skill_prerequisites"

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("question_categories.id"), nullable=False)
    prerequisite_id = db.Column(db.Integer, db.ForeignKey("question_categories.id"), nullable=False)
    min_mastery = db.Column(db.Float, nullable=False, default=60.0)

    category = db.relationship(
        "QuestionCategory",
        foreign_keys=[category_id],
        backref=db.backref("prerequisites", lazy=True),
    )
    prerequisite = db.relationship(
        "QuestionCategory",
        foreign_keys=[prerequisite_id],
        backref=db.backref("unlocks", lazy=True),
    )


DEFAULT_CATEGORY_NAMES: Sequence[tuple[str, str]] = (
    ("custom", "Personnalisé"),
    ("number_word", "Nombres ➜ mots"),
    ("word_number", "Mots ➜ nombres"),
    ("translate_fr_en", "Traduction FR ➜ EN"),
    ("translate_en_fr", "Traduction EN ➜ FR"),
    ("sentence_fr_en", "Phrase FR ➜ EN"),
    ("sentence_en_fr", "Phrase EN ➜ FR"),
    ("time_reading", "Dire l'heure"),
    ("calendar_vocab", "Jours et mois"),
    ("family_vocab", "La famille"),
    ("school_vocab", "L'école"),
    ("daily_routine", "Routine quotidienne"),
    ("hobbies_vocab", "Loisirs"),
    ("grammar_present_simple", "Grammaire : présent simple"),
    ("grammar_pronouns", "Grammaire : pronoms"),
    ("culture_countries", "Culture anglophone"),
    ("adjectives_opposites", "Adjectifs contraires"),
    ("interrogative_words", "Mots interrogatifs (when/what/who…)"),
    ("food_vocab", "Alimentation"),
    ("grammar_third_person_s", "Grammaire : 3e personne -s"),
    ("body_vocab", "Le corps"),
    ("clothes_vocab", "Les vêtements"),
    ("weather_vocab", "La météo"),
    ("ai_generated", "Généré par IA"),
)

DEFAULT_CATEGORY_METADATA: Dict[str, Dict[str, object]] = {
    "custom": {
        "domain": "production",
        "cecrl_level": "A1",
        "grade_level": "6e",
        "trimester": 1,
        "order_index": 1,
        "unlocked_by_default": True,
    },
    "number_word": {
        "domain": "vocabulary",
        "cecrl_level": "A1",
        "grade_level": "6e",
        "trimester": 1,
        "order_index": 2,
        "unlocked_by_default": True,
    },
    "word_number": {
        "domain": "vocabulary",
        "cecrl_level": "A1",
        "grade_level": "6e",
        "trimester": 1,
        "order_index": 3,
        "unlocked_by_default": True,
    },
    "translate_fr_en": {
        "domain": "production",
        "cecrl_level": "A1",
        "grade_level": "6e",
        "trimester": 1,
        "order_index": 4,
        "unlocked_by_default": True,
    },
    "translate_en_fr": {
        "domain": "comprehension",
        "cecrl_level": "A1",
        "grade_level": "6e",
        "trimester": 1,
        "order_index": 5,
        "unlocked_by_default": True,
    },
    "sentence_fr_en": {
        "domain": "production",
        "cecrl_level": "A2",
        "grade_level": "5e",
        "trimester": 1,
        "order_index": 10,
        "unlocked_by_default": False,
    },
    "sentence_en_fr": {
        "domain": "comprehension",
        "cecrl_level": "A2",
        "grade_level": "5e",
        "trimester": 1,
        "order_index": 9,
        "unlocked_by_default": False,
    },
    "time_reading": {
        "domain": "vocabulary",
        "cecrl_level": "A1",
        "grade_level": "6e",
        "trimester": 2,
        "order_index": 6,
        "unlocked_by_default": True,
    },
    "calendar_vocab": {
        "domain": "vocabulary",
        "cecrl_level": "A1",
        "grade_level": "6e",
        "trimester": 1,
        "order_index": 7,
        "unlocked_by_default": True,
    },
    "family_vocab": {
        "domain": "vocabulary",
        "cecrl_level": "A1",
        "grade_level": "6e",
        "trimester": 1,
        "order_index": 8,
        "unlocked_by_default": True,
    },
    "school_vocab": {
        "domain": "vocabulary",
        "cecrl_level": "A1",
        "grade_level": "6e",
        "trimester": 2,
        "order_index": 9,
        "unlocked_by_default": True,
    },
    "daily_routine": {
        "domain": "vocabulary",
        "cecrl_level": "A2",
        "grade_level": "6e",
        "trimester": 3,
        "order_index": 11,
        "unlocked_by_default": False,
    },
    "hobbies_vocab": {
        "domain": "vocabulary",
        "cecrl_level": "A2",
        "grade_level": "6e",
        "trimester": 3,
        "order_index": 12,
        "unlocked_by_default": False,
    },
    "grammar_present_simple": {
        "domain": "grammar",
        "cecrl_level": "A1",
        "grade_level": "6e",
        "trimester": 2,
        "order_index": 13,
        "unlocked_by_default": True,
    },
    "grammar_pronouns": {
        "domain": "grammar",
        "cecrl_level": "A1",
        "grade_level": "6e",
        "trimester": 1,
        "order_index": 14,
        "unlocked_by_default": True,
    },
    "culture_countries": {
        "domain": "culture",
        "cecrl_level": "A2",
        "grade_level": "5e",
        "trimester": 2,
        "order_index": 15,
        "unlocked_by_default": False,
    },
    "adjectives_opposites": {
        "domain": "vocabulary",
        "cecrl_level": "A2",
        "grade_level": "6e",
        "trimester": 3,
        "order_index": 16,
        "unlocked_by_default": False,
    },
    "interrogative_words": {
        "domain": "grammar",
        "cecrl_level": "A1",
        "grade_level": "6e",
        "trimester": 2,
        "order_index": 17,
        "unlocked_by_default": True,
    },
    "food_vocab": {
        "domain": "vocabulary",
        "cecrl_level": "A1",
        "grade_level": "6e",
        "trimester": 2,
        "order_index": 18,
        "unlocked_by_default": True,
    },
    "grammar_third_person_s": {
        "domain": "grammar",
        "cecrl_level": "A1",
        "grade_level": "6e",
        "trimester": 2,
        "order_index": 19,
        "unlocked_by_default": True,
    },
    "body_vocab": {
        "domain": "vocabulary",
        "cecrl_level": "A1",
        "grade_level": "6e",
        "trimester": 1,
        "order_index": 20,
        "unlocked_by_default": True,
    },
    "clothes_vocab": {
        "domain": "vocabulary",
        "cecrl_level": "A1",
        "grade_level": "6e",
        "trimester": 2,
        "order_index": 21,
        "unlocked_by_default": True,
    },
    "weather_vocab": {
        "domain": "vocabulary",
        "cecrl_level": "A1",
        "grade_level": "6e",
        "trimester": 1,
        "order_index": 22,
        "unlocked_by_default": True,
    },
    "ai_generated": {
        "domain": "mixed",
        "cecrl_level": "A1",
        "grade_level": "6e",
        "trimester": 1,
        "order_index": 23,
        "unlocked_by_default": True,
    },
}
