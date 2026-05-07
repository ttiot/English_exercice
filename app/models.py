from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional, Sequence

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
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

    sessions = db.relationship("PracticeSession", backref="student", lazy=True)

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


class OpenAIConfig(db.Model, TimestampMixin):
    """Singleton stockant la configuration OpenAI globale modifiable depuis l'admin.

    La clé API est chiffrée avec Fernet (cf. `Config.FERNET_KEY`). Si aucune
    ligne n'est `is_active=True`, le service IA retombe sur les variables
    d'environnement `OPENAI_*`.
    """

    __tablename__ = "openai_config"

    id = db.Column(db.Integer, primary_key=True)
    api_key_encrypted = db.Column(db.Text, nullable=True)
    base_url = db.Column(
        db.String(500), nullable=True, default="https://api.openai.com/v1"
    )
    default_model = db.Column(db.String(100), nullable=True, default="gpt-4o-mini")
    source_name = db.Column(db.String(100), nullable=True, default="OpenAI")
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    monthly_budget_usd = db.Column(db.Numeric(10, 2), nullable=True)

    def set_api_key(self, api_key: Optional[str]) -> None:
        """Chiffre et stocke la clé API. Vide / None ⇒ supprime la clé."""
        if not api_key:
            self.api_key_encrypted = None
            return

        from cryptography.fernet import Fernet
        from flask import current_app

        key = current_app.config.get("FERNET_KEY")
        if not key:
            current_app.logger.warning(
                "FERNET_KEY non définie, la clé OpenAI n'a pas été chiffrée."
            )
            return

        if isinstance(key, str):
            key = key.encode()

        cipher = Fernet(key)
        self.api_key_encrypted = cipher.encrypt(api_key.encode()).decode()

    def get_api_key(self) -> Optional[str]:
        """Retourne la clé API en clair, ou None si absente / illisible."""
        if not self.api_key_encrypted:
            return None

        from cryptography.fernet import Fernet
        from flask import current_app

        key = current_app.config.get("FERNET_KEY")
        if not key:
            return None

        if isinstance(key, str):
            key = key.encode()

        try:
            cipher = Fernet(key)
            return cipher.decrypt(self.api_key_encrypted.encode()).decode()
        except Exception:
            # Clé Fernet rotée → ciphertext illisible. On le signale par None.
            return None

    @staticmethod
    def get_active() -> Optional["OpenAIConfig"]:
        return OpenAIConfig.query.filter_by(is_active=True).first()

    @staticmethod
    def get_or_create() -> "OpenAIConfig":
        config = OpenAIConfig.query.first()
        if not config:
            config = OpenAIConfig()
            db.session.add(config)
            db.session.commit()
        return config


class AICallLog(db.Model):
    """Audit + base du tracking budget des appels OpenAI."""

    __tablename__ = "ai_call_log"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id"), nullable=True, index=True
    )
    call_type = db.Column(db.String(50), nullable=False, index=True)
    model = db.Column(db.String(100), nullable=False)
    api_key_source = db.Column(db.String(20), nullable=False, default="global")

    system_prompt = db.Column(db.Text, nullable=True)
    user_prompt = db.Column(db.Text, nullable=True)
    response_text = db.Column(db.Text, nullable=True)
    response_status = db.Column(db.String(20), nullable=False, default="success")
    error_message = db.Column(db.Text, nullable=True)

    input_tokens = db.Column(db.Integer, nullable=True)
    output_tokens = db.Column(db.Integer, nullable=True)
    total_tokens = db.Column(db.Integer, nullable=True)
    estimated_cost_usd = db.Column(db.Numeric(10, 6), nullable=True)

    duration_ms = db.Column(db.Integer, nullable=True)
    context_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False, index=True
    )

    student = db.relationship(
        "Student", backref=db.backref("ai_call_logs", lazy="dynamic")
    )

    # Tarifs USD par 1k tokens. Mots-clés cherchés en sous-chaîne dans `model`.
    # À tenir à jour selon https://openai.com/api/pricing/.
    TOKEN_PRICES = {
        "gpt-5.2": {"input": 0.005, "output": 0.02},
        "gpt-5.1": {"input": 0.004, "output": 0.016},
        "gpt-5-mini": {"input": 0.0003, "output": 0.0012},
        "gpt-5": {"input": 0.003, "output": 0.012},
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        "gpt-4o": {"input": 0.0025, "output": 0.01},
        "gpt-4-turbo": {"input": 0.01, "output": 0.03},
        "gpt-4": {"input": 0.03, "output": 0.06},
        "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
        "o1-mini": {"input": 0.003, "output": 0.012},
        "o1": {"input": 0.015, "output": 0.06},
    }

    @staticmethod
    def _calculate_cost(
        model: str,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
    ) -> Optional[Decimal]:
        if not model or input_tokens is None or output_tokens is None:
            return None
        model_lower = model.lower()
        prices = None
        for key, value in AICallLog.TOKEN_PRICES.items():
            if key in model_lower:
                prices = value
                break
        if not prices:
            return None
        input_cost = (input_tokens / 1000) * prices.get("input", 0)
        output_cost = (output_tokens / 1000) * prices.get("output", 0)
        return Decimal(str(round(input_cost + output_cost, 6)))

    @staticmethod
    def log_call(
        student_id: Optional[int],
        call_type: str,
        model: str,
        api_key_source: str = "global",
        system_prompt: Optional[str] = None,
        user_prompt: Optional[str] = None,
        response_text: Optional[str] = None,
        response_status: str = "success",
        error_message: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        duration_ms: Optional[int] = None,
        context_json: Optional[str] = None,
    ) -> "AICallLog":
        total_tokens = None
        if input_tokens is not None and output_tokens is not None:
            total_tokens = input_tokens + output_tokens
        log = AICallLog(
            student_id=student_id,
            call_type=call_type,
            model=model,
            api_key_source=api_key_source,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_text=response_text,
            response_status=response_status,
            error_message=error_message,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=AICallLog._calculate_cost(
                model, input_tokens, output_tokens
            ),
            duration_ms=duration_ms,
            context_json=context_json,
        )
        db.session.add(log)
        return log

    @staticmethod
    def get_monthly_cost_usd(
        year: Optional[int] = None, month: Optional[int] = None
    ) -> Decimal:
        from sqlalchemy import func, extract

        if year is None or month is None:
            now = datetime.utcnow()
            year = now.year
            month = now.month
        result = (
            db.session.query(func.sum(AICallLog.estimated_cost_usd))
            .filter(
                extract("year", AICallLog.created_at) == year,
                extract("month", AICallLog.created_at) == month,
            )
            .scalar()
        )
        return Decimal(str(result)) if result else Decimal("0")

    @staticmethod
    def get_monthly_stats(
        year: Optional[int] = None, month: Optional[int] = None
    ) -> dict:
        from sqlalchemy import func, extract

        if year is None or month is None:
            now = datetime.utcnow()
            year = now.year
            month = now.month
        totals = (
            db.session.query(
                func.count(AICallLog.id).label("calls"),
                func.sum(AICallLog.input_tokens).label("input_tokens"),
                func.sum(AICallLog.output_tokens).label("output_tokens"),
                func.sum(AICallLog.estimated_cost_usd).label("cost"),
            )
            .filter(
                extract("year", AICallLog.created_at) == year,
                extract("month", AICallLog.created_at) == month,
            )
            .first()
        )
        by_type = (
            db.session.query(
                AICallLog.call_type,
                func.count(AICallLog.id).label("calls"),
                func.sum(AICallLog.estimated_cost_usd).label("cost"),
            )
            .filter(
                extract("year", AICallLog.created_at) == year,
                extract("month", AICallLog.created_at) == month,
            )
            .group_by(AICallLog.call_type)
            .all()
        )
        return {
            "year": year,
            "month": month,
            "calls": totals.calls or 0,
            "input_tokens": int(totals.input_tokens or 0),
            "output_tokens": int(totals.output_tokens or 0),
            "cost_usd": float(totals.cost) if totals.cost else 0.0,
            "by_type": [
                {
                    "type": row.call_type,
                    "calls": row.calls,
                    "cost_usd": float(row.cost) if row.cost else 0.0,
                }
                for row in by_type
            ],
        }


class AIGeneratedExercise(db.Model, TimestampMixin):
    """Pool des exercices générés par OpenAI, conservés pour réutilisation.

    Chaque ligne capture l'énoncé final + la réponse + le prompt brut tapé
    par l'élève qui a déclenché la génération. `times_used` est incrémenté
    à chaque session qui repioche l'exercice ; `is_disabled` permet à un
    parent de retirer un exo douteux du pool sans casser les sessions
    historiques (elles gardent leur copie dans `session_exercises`).
    """

    __tablename__ = "ai_generated_exercises"

    id = db.Column(db.Integer, primary_key=True)
    student_prompt = db.Column(db.Text, nullable=False)
    prompt = db.Column(db.Text, nullable=False)
    answer = db.Column(db.String(500), nullable=False)
    category_code = db.Column(db.String(80), nullable=False, index=True)
    question_type = db.Column(db.String(20), nullable=False, default="text")
    options_json = db.Column(db.Text, nullable=True)
    accepted_answers_json = db.Column(db.Text, nullable=True)
    difficulty = db.Column(db.String(20), nullable=False, default="beginner", index=True)
    model_used = db.Column(db.String(100), nullable=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id"), nullable=True, index=True
    )
    call_log_id = db.Column(
        db.Integer, db.ForeignKey("ai_call_log.id"), nullable=True
    )
    times_used = db.Column(db.Integer, nullable=False, default=0)
    is_disabled = db.Column(db.Boolean, nullable=False, default=False, index=True)

    student = db.relationship(
        "Student", backref=db.backref("ai_generated_exercises", lazy="dynamic")
    )
    call_log = db.relationship("AICallLog")


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


def ensure_schema_migrations() -> None:
    inspector = inspect(db.engine)
    table_names = inspector.get_table_names()

    needs_commit = False

    if "students" in table_names:
        student_columns = {
            column["name"] for column in inspector.get_columns("students")
        }

        if "email" not in student_columns:
            db.session.execute(
                text("ALTER TABLE students ADD COLUMN email VARCHAR(255)")
            )
            needs_commit = True

        if "role" not in student_columns:
            db.session.execute(
                text("ALTER TABLE students ADD COLUMN role VARCHAR(20) DEFAULT 'student'")
            )
            db.session.execute(
                text(
                    "UPDATE students SET role = 'student' WHERE role IS NULL"
                )
            )
            needs_commit = True

        if "avatar_filename" not in student_columns:
            db.session.execute(
                text("ALTER TABLE students ADD COLUMN avatar_filename VARCHAR(255)")
            )
            needs_commit = True

        if "pin_hash" not in student_columns:
            default_hash = generate_password_hash("0000")
            db.session.execute(
                text("ALTER TABLE students ADD COLUMN pin_hash VARCHAR(255) DEFAULT :hash"),
                {"hash": default_hash}
            )
            db.session.execute(
                text("UPDATE students SET pin_hash = :hash WHERE pin_hash IS NULL"),
                {"hash": default_hash}
            )
            needs_commit = True

        if "target_cefr_level" not in student_columns:
            db.session.execute(
                text("ALTER TABLE students ADD COLUMN target_cefr_level VARCHAR(10)")
            )
            needs_commit = True

        if "target_grade" not in student_columns:
            db.session.execute(
                text("ALTER TABLE students ADD COLUMN target_grade VARCHAR(10)")
            )
            needs_commit = True

        if "target_trimester" not in student_columns:
            db.session.execute(
                text("ALTER TABLE students ADD COLUMN target_trimester INTEGER")
            )
            needs_commit = True

        if "interests" not in student_columns:
            db.session.execute(
                text("ALTER TABLE students ADD COLUMN interests TEXT")
            )
            needs_commit = True

        if "preferred_domains" not in student_columns:
            db.session.execute(
                text("ALTER TABLE students ADD COLUMN preferred_domains VARCHAR(255)")
            )
            needs_commit = True

    if "practice_sessions" in table_names:
        session_columns = {
            column["name"] for column in inspector.get_columns("practice_sessions")
        }

        if "time_limit_minutes" not in session_columns:
            db.session.execute(
                text("ALTER TABLE practice_sessions ADD COLUMN time_limit_minutes INTEGER")
            )
            needs_commit = True

        if "duration_seconds" not in session_columns:
            db.session.execute(
                text("ALTER TABLE practice_sessions ADD COLUMN duration_seconds INTEGER")
            )
            needs_commit = True

        if "time_limit_seconds" not in session_columns:
            db.session.execute(
                text("ALTER TABLE practice_sessions ADD COLUMN time_limit_seconds INTEGER")
            )
            needs_commit = True

        if "difficulty" not in session_columns:
            db.session.execute(
                text(
                    "ALTER TABLE practice_sessions ADD COLUMN difficulty VARCHAR(20) DEFAULT 'beginner'"
                )
            )
            db.session.execute(
                text(
                    "UPDATE practice_sessions SET difficulty = 'beginner' WHERE difficulty IS NULL"
                )
            )
            needs_commit = True

        if "session_type" not in session_columns:
            db.session.execute(
                text("ALTER TABLE practice_sessions ADD COLUMN session_type VARCHAR(20) DEFAULT 'practice'")
            )
            db.session.execute(
                text("UPDATE practice_sessions SET session_type = 'practice' WHERE session_type IS NULL")
            )
            needs_commit = True

        if "instructions_fr" not in session_columns:
            db.session.execute(
                text("ALTER TABLE practice_sessions ADD COLUMN instructions_fr TEXT")
            )
            needs_commit = True

        if "instructions_en" not in session_columns:
            db.session.execute(
                text("ALTER TABLE practice_sessions ADD COLUMN instructions_en TEXT")
            )
            needs_commit = True

    if "question_categories" in table_names:
        category_columns = {
            column["name"] for column in inspector.get_columns("question_categories")
        }

        if "domain" not in category_columns:
            db.session.execute(
                text("ALTER TABLE question_categories ADD COLUMN domain VARCHAR(50)")
            )
            needs_commit = True

    if "student_skill_progress" in table_names:
        progress_columns = {
            column["name"] for column in inspector.get_columns("student_skill_progress")
        }

        nullable_fixups = {
            "mastery": 0.0,
            "total_attempts": 0,
            "correct_attempts": 0,
            "correct_streak": 0,
        }
        for column_name, default_value in nullable_fixups.items():
            if column_name in progress_columns:
                db.session.execute(
                    text(
                        f"UPDATE student_skill_progress SET {column_name} = :value "
                        f"WHERE {column_name} IS NULL"
                    ),
                    {"value": default_value},
                )
                needs_commit = True

        if "cecrl_level" not in category_columns:
            db.session.execute(
                text("ALTER TABLE question_categories ADD COLUMN cecrl_level VARCHAR(10)")
            )
            needs_commit = True

        if "grade_level" not in category_columns:
            db.session.execute(
                text("ALTER TABLE question_categories ADD COLUMN grade_level VARCHAR(10)")
            )
            needs_commit = True

        if "trimester" not in category_columns:
            db.session.execute(
                text("ALTER TABLE question_categories ADD COLUMN trimester INTEGER")
            )
            needs_commit = True

        if "order_index" not in category_columns:
            db.session.execute(
                text("ALTER TABLE question_categories ADD COLUMN order_index INTEGER")
            )
            needs_commit = True

        if "unlocked_by_default" not in category_columns:
            db.session.execute(
                text("ALTER TABLE question_categories ADD COLUMN unlocked_by_default BOOLEAN DEFAULT 1")
            )
            db.session.execute(
                text("UPDATE question_categories SET unlocked_by_default = 1 WHERE unlocked_by_default IS NULL")
            )
            needs_commit = True

    if "prepared_exercise_sets" in table_names:
        prepared_columns = {
            column["name"] for column in inspector.get_columns("prepared_exercise_sets")
        }

        if "instructions_fr" not in prepared_columns:
            db.session.execute(
                text("ALTER TABLE prepared_exercise_sets ADD COLUMN instructions_fr TEXT")
            )
            needs_commit = True

        if "instructions_en" not in prepared_columns:
            db.session.execute(
                text("ALTER TABLE prepared_exercise_sets ADD COLUMN instructions_en TEXT")
            )
            needs_commit = True

    if "exercise_items" in table_names:
        item_columns = {
            column["name"] for column in inspector.get_columns("exercise_items")
        }

        if "is_active" not in item_columns:
            db.session.execute(
                text("ALTER TABLE exercise_items ADD COLUMN is_active BOOLEAN DEFAULT 1")
            )
            db.session.execute(
                text("UPDATE exercise_items SET is_active = 1 WHERE is_active IS NULL")
            )
            needs_commit = True

    if "session_exercises" in table_names:
        session_ex_columns = {
            column["name"] for column in inspector.get_columns("session_exercises")
        }
        if "question_type" not in session_ex_columns:
            db.session.execute(
                text(
                    "ALTER TABLE session_exercises ADD COLUMN question_type "
                    "VARCHAR(20) DEFAULT 'text'"
                )
            )
            db.session.execute(
                text(
                    "UPDATE session_exercises SET question_type = 'text' "
                    "WHERE question_type IS NULL"
                )
            )
            needs_commit = True
        if "options_json" not in session_ex_columns:
            db.session.execute(
                text("ALTER TABLE session_exercises ADD COLUMN options_json TEXT")
            )
            needs_commit = True
        if "accepted_answers_json" not in session_ex_columns:
            db.session.execute(
                text(
                    "ALTER TABLE session_exercises ADD COLUMN accepted_answers_json TEXT"
                )
            )
            needs_commit = True
        if "source" not in session_ex_columns:
            db.session.execute(
                text(
                    "ALTER TABLE session_exercises ADD COLUMN source "
                    "VARCHAR(20) DEFAULT 'procedural'"
                )
            )
            db.session.execute(
                text(
                    "UPDATE session_exercises SET source = 'procedural' "
                    "WHERE source IS NULL"
                )
            )
            needs_commit = True
        if "ai_exercise_id" not in session_ex_columns:
            db.session.execute(
                text("ALTER TABLE session_exercises ADD COLUMN ai_exercise_id INTEGER")
            )
            needs_commit = True

    if needs_commit:
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


__all__ = [
    "Student",
    "PracticeSession",
    "SessionExercise",
    "PreparedExercise",
    "PreparedExerciseSet",
    "PreparedExerciseQuestion",
    "ExerciseItem",
    "QuestionCategory",
    "WeeklyGoal",
    "Badge",
    "StudentBadge",
    "ReviewPlan",
    "SkillPrerequisite",
    "StudentSkillProgress",
    "OpenAIConfig",
    "AICallLog",
    "AIGeneratedExercise",
    "ensure_default_badges",
    "ensure_default_categories",
    "ensure_default_prerequisites",
    "ensure_schema_migrations",
    "ensure_admin_account",
]
