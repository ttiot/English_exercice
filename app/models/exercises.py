"""Sessions de pratique, exercices joués, exercices préparés et items de banque."""

from datetime import datetime
from typing import Optional

from ..extensions import db
from .core import Student, TimestampMixin


class PracticeSession(db.Model, TimestampMixin):
    __tablename__ = "practice_sessions"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    time_limit_minutes = db.Column(db.Integer, nullable=True)
    time_limit_seconds = db.Column(db.Integer, nullable=True)
    total_questions = db.Column(db.Integer, nullable=False, default=0)
    correct_answers = db.Column(db.Integer, nullable=False, default=0)
    difficulty = db.Column(db.String(20), nullable=False, default="beginner")
    duration_seconds = db.Column(db.Integer, nullable=True)
    session_type = db.Column(db.String(20), nullable=False, default="practice")
    instructions_fr = db.Column(db.Text, nullable=True)
    instructions_en = db.Column(db.Text, nullable=True)

    exercises = db.relationship(
        "SessionExercise",
        backref="session",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="SessionExercise.display_order",
    )

    def completion_rate(self) -> float:
        if not self.total_questions:
            return 0.0
        return (self.correct_answers / self.total_questions) * 100


class SessionExercise(db.Model, TimestampMixin):
    __tablename__ = "session_exercises"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("practice_sessions.id"), nullable=False)
    prompt = db.Column(db.Text, nullable=False)
    correct_answer = db.Column(db.String(255), nullable=False)
    student_answer = db.Column(db.String(255), nullable=True)
    category = db.Column(db.String(50), nullable=False)
    is_correct = db.Column(db.Boolean, default=False, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)
    # Format de question : 'text' (libre, défaut), 'mcq' (choix unique parmi
    # `options_json`), 'word_bank' (saisie libre + banque de mots affichée).
    question_type = db.Column(db.String(20), nullable=False, default="text")
    # Liste JSON des options affichées (QCM ou banque de mots).
    options_json = db.Column(db.Text, nullable=True)
    # Liste JSON de variantes de réponse acceptées en plus de `correct_answer`.
    accepted_answers_json = db.Column(db.Text, nullable=True)
    # Explication pédagogique courte (fournie par l'IA), affichée en correction.
    explanation = db.Column(db.Text, nullable=True)
    # Statut fin de correction : 'correct', 'near_miss' ou 'incorrect'.
    correction_status = db.Column(db.String(20), nullable=False, default="incorrect")
    # Origine de l'exercice : 'procedural', 'ai', 'prepared'.
    source = db.Column(db.String(20), nullable=False, default="procedural")
    # FK optionnelle vers le pool d'exercices IA (pour la traçabilité).
    ai_exercise_id = db.Column(
        db.Integer, db.ForeignKey("ai_generated_exercises.id"), nullable=True
    )

    @property
    def options(self) -> list:
        """Liste affichable des options (QCM/word bank), ou liste vide."""
        if not self.options_json:
            return []
        import json as _json

        try:
            data = _json.loads(self.options_json)
            return list(data) if isinstance(data, list) else []
        except (ValueError, TypeError):
            return []


class PreparedExercise(db.Model, TimestampMixin):
    __tablename__ = "prepared_exercises"

    id = db.Column(db.Integer, primary_key=True)
    prompt = db.Column(db.Text, nullable=False)
    answer = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(50), nullable=False, default="custom")
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=True)
    is_used = db.Column(db.Boolean, default=False, nullable=False)

    student = db.relationship("Student", backref=db.backref("prepared_exercises", lazy=True))

    def assign_to(self, student: Optional[Student]) -> None:
        self.student = student


class PreparedExerciseSet(db.Model, TimestampMixin):
    __tablename__ = "prepared_exercise_sets"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=True)
    is_used = db.Column(db.Boolean, default=False, nullable=False)
    use_time_limit = db.Column(db.Boolean, default=False, nullable=False)
    time_limit_seconds = db.Column(db.Integer, nullable=True)
    instructions_fr = db.Column(db.Text, nullable=True)
    instructions_en = db.Column(db.Text, nullable=True)

    student = db.relationship("Student", backref=db.backref("prepared_sets", lazy=True))
    questions = db.relationship(
        "PreparedExerciseQuestion",
        backref="exercise_set",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="PreparedExerciseQuestion.position",
    )

    def mark_used(self) -> None:
        self.is_used = True


class PreparedExerciseQuestion(db.Model, TimestampMixin):
    __tablename__ = "prepared_exercise_questions"

    id = db.Column(db.Integer, primary_key=True)
    exercise_set_id = db.Column(
        db.Integer, db.ForeignKey("prepared_exercise_sets.id"), nullable=False
    )
    prompt = db.Column(db.Text, nullable=False)
    answer = db.Column(db.String(255), nullable=False)
    category_code = db.Column(db.String(80), nullable=False, default="custom")
    position = db.Column(db.Integer, nullable=False, default=0)


class ExerciseItem(db.Model, TimestampMixin):
    __tablename__ = "exercise_items"

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("question_categories.id"), nullable=False)
    difficulty = db.Column(db.String(20), nullable=False, default="beginner")
    prompt = db.Column(db.Text, nullable=False)
    answer = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    category = db.relationship("QuestionCategory", backref=db.backref("exercise_items", lazy=True))
