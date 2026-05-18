"""Progression de l'élève : objectifs, badges, planning de révision."""

from datetime import datetime

from ..extensions import db
from .core import TimestampMixin


class WeeklyGoal(db.Model, TimestampMixin):
    __tablename__ = "weekly_goals"
    __table_args__ = (
        db.UniqueConstraint("student_id", "week_start", name="uq_weekly_goal_student_week"),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    week_start = db.Column(db.Date, nullable=False)
    target_sessions = db.Column(db.Integer, nullable=False, default=3)
    target_minutes = db.Column(db.Integer, nullable=False, default=45)
    target_accuracy = db.Column(db.Float, nullable=False, default=70.0)
    target_challenges = db.Column(db.Integer, nullable=False, default=1)

    student = db.relationship("Student", backref=db.backref("weekly_goals", lazy=True))


class Badge(db.Model, TimestampMixin):
    __tablename__ = "badges"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey("question_categories.id"), nullable=True)
    min_mastery = db.Column(db.Float, nullable=False, default=80.0)
    min_streak = db.Column(db.Integer, nullable=False, default=2)

    category = db.relationship("QuestionCategory", backref=db.backref("badges", lazy=True))


class StudentBadge(db.Model, TimestampMixin):
    __tablename__ = "student_badges"
    __table_args__ = (
        db.UniqueConstraint("student_id", "badge_id", name="uq_student_badge"),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    badge_id = db.Column(db.Integer, db.ForeignKey("badges.id"), nullable=False)
    awarded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    student = db.relationship("Student", backref=db.backref("badges", lazy=True))
    badge = db.relationship("Badge", backref=db.backref("awards", lazy=True))


class ReviewPlan(db.Model, TimestampMixin):
    __tablename__ = "review_plans"
    __table_args__ = (
        db.UniqueConstraint(
            "student_id", "category_id", "due_date", name="uq_review_plan_student_category_date"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("question_categories.id"), nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    completed = db.Column(db.Boolean, default=False, nullable=False)

    student = db.relationship("Student", backref=db.backref("review_plans", lazy=True))
    category = db.relationship("QuestionCategory", backref=db.backref("review_plans", lazy=True))


class StudentSkillProgress(db.Model, TimestampMixin):
    __tablename__ = "student_skill_progress"
    __table_args__ = (
        db.UniqueConstraint("student_id", "category_id", name="uq_skill_progress_student_category"),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("question_categories.id"), nullable=False)
    mastery = db.Column(db.Float, nullable=False, default=0.0)
    total_attempts = db.Column(db.Integer, nullable=False, default=0)
    correct_attempts = db.Column(db.Integer, nullable=False, default=0)
    correct_streak = db.Column(db.Integer, nullable=False, default=0)
    last_accuracy = db.Column(db.Float, nullable=True)
    last_practiced = db.Column(db.DateTime, nullable=True)

    student = db.relationship("Student", backref=db.backref("skill_progress", lazy=True))
    category = db.relationship("QuestionCategory", backref=db.backref("skill_progress", lazy=True))
