from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import inspect, text
from werkzeug.security import check_password_hash, generate_password_hash

from . import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class Student(db.Model, TimestampMixin):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(120), nullable=False)
    last_name = db.Column(db.String(120), nullable=True)
    age = db.Column(db.Integer, nullable=True)
    goals = db.Column(db.Text, nullable=True)
    avatar_filename = db.Column(db.String(255), nullable=True)
    pin_hash = db.Column(db.String(255), nullable=False)

    sessions = db.relationship("PracticeSession", backref="student", lazy=True)

    def full_name(self) -> str:
        if self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name

    def set_pin(self, pin_code: str) -> None:
        self.pin_hash = generate_password_hash(pin_code)

    def check_pin(self, pin_code: str) -> bool:
        if not self.pin_hash:
            return False
        return check_password_hash(self.pin_hash, pin_code)

    def avatar_url(self) -> str:
        if self.avatar_filename:
            return f"uploads/{self.avatar_filename}"
        return "img/default_avatar.svg"


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


class QuestionCategory(db.Model, TimestampMixin):
    __tablename__ = "question_categories"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(80), nullable=False, unique=True)
    name = db.Column(db.String(120), nullable=False, unique=True)

    def __repr__(self) -> str:  # pragma: no cover - repr utility
        return f"<QuestionCategory {self.code}>"


class PreparedExerciseSet(db.Model, TimestampMixin):
    __tablename__ = "prepared_exercise_sets"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=True)
    is_used = db.Column(db.Boolean, default=False, nullable=False)
    use_time_limit = db.Column(db.Boolean, default=False, nullable=False)
    time_limit_seconds = db.Column(db.Integer, nullable=True)

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


class ParentCredential(db.Model, TimestampMixin):
    __tablename__ = "parent_credentials"

    id = db.Column(db.Integer, primary_key=True)
    password_hash = db.Column(db.String(255), nullable=False)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


DEFAULT_CATEGORY_NAMES: Sequence[tuple[str, str]] = (
    ("custom", "Personnalisé"),
    ("number_word", "Nombres ➜ mots"),
    ("word_number", "Mots ➜ nombres"),
    ("translate_fr_en", "Traduction FR ➜ EN"),
    ("translate_en_fr", "Traduction EN ➜ FR"),
    ("sentence_fr_en", "Phrase FR ➜ EN"),
    ("sentence_en_fr", "Phrase EN ➜ FR"),
)


def ensure_default_categories() -> None:
    if QuestionCategory.query.count() == 0:
        for code, name in DEFAULT_CATEGORY_NAMES:
            db.session.add(QuestionCategory(code=code, name=name))
        db.session.commit()


def ensure_parent_credentials(default_password: str) -> None:
    credential = ParentCredential.query.first()
    if not credential:
        credential = ParentCredential()
        credential.set_password(default_password)
        db.session.add(credential)
        db.session.commit()


def ensure_schema_migrations() -> None:
    inspector = inspect(db.engine)
    table_names = inspector.get_table_names()

    if "students" not in table_names:
        return

    columns = {column["name"] for column in inspector.get_columns("students")}
    needs_commit = False

    if "avatar_filename" not in columns:
        db.session.execute(text("ALTER TABLE students ADD COLUMN avatar_filename VARCHAR(255)"))
        needs_commit = True

    if "pin_hash" not in columns:
        default_hash = generate_password_hash("0000").replace("'", "''")
        db.session.execute(
            text(
                "ALTER TABLE students ADD COLUMN pin_hash VARCHAR(255) DEFAULT '"
                + default_hash
                + "'"
            )
        )
        db.session.execute(
            text(
                "UPDATE students SET pin_hash = '"
                + default_hash
                + "' WHERE pin_hash IS NULL"
            )
        )
        needs_commit = True

    if needs_commit:
        db.session.commit()


__all__ = [
    "Student",
    "PracticeSession",
    "SessionExercise",
    "PreparedExercise",
    "PreparedExerciseSet",
    "PreparedExerciseQuestion",
    "QuestionCategory",
    "ParentCredential",
    "ensure_default_categories",
    "ensure_parent_credentials",
    "ensure_schema_migrations",
]
