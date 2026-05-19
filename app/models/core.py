"""Mixin de timestamps, table d'association parent_student et modèle Student."""

from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


parent_student = db.Table(
    "parent_student",
    db.Column("parent_id", db.Integer, db.ForeignKey("students.id"), primary_key=True),
    db.Column("student_id", db.Integer, db.ForeignKey("students.id"), primary_key=True),
)


class Student(db.Model, TimestampMixin):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(120), nullable=False)
    last_name = db.Column(db.String(120), nullable=True)
    email = db.Column(db.String(255), unique=True, nullable=True)
    role = db.Column(db.String(20), nullable=False, default="student")
    age = db.Column(db.Integer, nullable=True)
    goals = db.Column(db.Text, nullable=True)
    target_cefr_level = db.Column(db.String(10), nullable=True)
    target_grade = db.Column(db.String(10), nullable=True)
    target_trimester = db.Column(db.Integer, nullable=True)
    interests = db.Column(db.Text, nullable=True)
    preferred_domains = db.Column(db.String(255), nullable=True)
    avatar_filename = db.Column(db.String(255), nullable=True)
    password_hash = db.Column("pin_hash", db.String(255), nullable=False)
    reset_token_hash = db.Column(db.String(255), nullable=True)
    reset_token_expires_at = db.Column(db.DateTime, nullable=True)

    sessions = db.relationship("PracticeSession", backref="student", lazy=True)

    managed_students = db.relationship(
        "Student",
        secondary=parent_student,
        primaryjoin="Student.id == parent_student.c.parent_id",
        secondaryjoin="Student.id == parent_student.c.student_id",
        backref="parents",
    )

    def full_name(self) -> str:
        if self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def is_parent(self) -> bool:
        return self.role == "parent"

    def is_admin(self) -> bool:
        return self.role == "admin"

    def avatar_url(self) -> str:
        if self.avatar_filename:
            return f"uploads/{self.avatar_filename}"
        return "img/default_avatar.svg"
