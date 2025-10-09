from datetime import datetime
from typing import Optional

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

    sessions = db.relationship("PracticeSession", backref="student", lazy=True)

    def full_name(self) -> str:
        if self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name


class PracticeSession(db.Model, TimestampMixin):
    __tablename__ = "practice_sessions"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    time_limit_minutes = db.Column(db.Integer, nullable=True)
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


__all__ = [
    "Student",
    "PracticeSession",
    "SessionExercise",
    "PreparedExercise",
]
