"""Modèles liés à l'IA : config OpenAI, prompts éditables, logs d'appels,
exercices générés et cache de traductions.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from ..extensions import db
from .core import Student, TimestampMixin
from .utils import _safe_format


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

    @staticmethod
    def get_yearly_trend(months: int = 12) -> list:
        """Renvoie une liste chronologique de ``months`` dicts mensuels.

        Chaque entrée : ``{year, month, label, calls, cost_usd, total_tokens}``.
        Trié du plus ancien au plus récent. Les mois sans appel apparaissent
        avec des compteurs à 0.
        """
        from sqlalchemy import func, extract

        now = datetime.utcnow()
        buckets: list = []
        for offset in range(months - 1, -1, -1):
            year = now.year
            month = now.month - offset
            while month <= 0:
                month += 12
                year -= 1
            row = (
                db.session.query(
                    func.count(AICallLog.id).label("calls"),
                    func.sum(AICallLog.estimated_cost_usd).label("cost"),
                    func.sum(AICallLog.total_tokens).label("tokens"),
                )
                .filter(
                    extract("year", AICallLog.created_at) == year,
                    extract("month", AICallLog.created_at) == month,
                )
                .first()
            )
            buckets.append(
                {
                    "year": year,
                    "month": month,
                    "label": f"{year:04d}-{month:02d}",
                    "calls": int(row.calls or 0) if row else 0,
                    "cost_usd": float(row.cost) if row and row.cost else 0.0,
                    "total_tokens": int(row.tokens or 0) if row else 0,
                }
            )
        return buckets

    @staticmethod
    def get_top_students(
        limit: int = 10,
        year: Optional[int] = None,
        month: Optional[int] = None,
    ) -> list:
        """Top ``limit`` élèves par coût mensuel (mois courant par défaut)."""
        from sqlalchemy import func, extract

        if year is None or month is None:
            now = datetime.utcnow()
            year = now.year
            month = now.month

        rows = (
            db.session.query(
                AICallLog.student_id,
                func.count(AICallLog.id).label("calls"),
                func.sum(AICallLog.estimated_cost_usd).label("cost"),
                func.sum(AICallLog.total_tokens).label("tokens"),
            )
            .filter(
                AICallLog.student_id.isnot(None),
                extract("year", AICallLog.created_at) == year,
                extract("month", AICallLog.created_at) == month,
            )
            .group_by(AICallLog.student_id)
            .order_by(func.sum(AICallLog.estimated_cost_usd).desc().nullslast())
            .limit(limit)
            .all()
        )
        student_ids = [row.student_id for row in rows]
        students = (
            {s.id: s for s in Student.query.filter(Student.id.in_(student_ids)).all()}
            if student_ids
            else {}
        )
        result = []
        for row in rows:
            student = students.get(row.student_id)
            result.append(
                {
                    "student_id": row.student_id,
                    "full_name": student.full_name() if student else "—",
                    "calls": int(row.calls or 0),
                    "cost_usd": float(row.cost) if row.cost else 0.0,
                    "total_tokens": int(row.tokens or 0),
                }
            )
        return result

    @staticmethod
    def get_success_stats(
        year: Optional[int] = None, month: Optional[int] = None
    ) -> dict:
        """Compteurs ``{success, error, total, success_rate}`` pour un mois."""
        from sqlalchemy import func, extract

        if year is None or month is None:
            now = datetime.utcnow()
            year = now.year
            month = now.month

        rows = (
            db.session.query(
                AICallLog.response_status,
                func.count(AICallLog.id).label("count"),
            )
            .filter(
                extract("year", AICallLog.created_at) == year,
                extract("month", AICallLog.created_at) == month,
            )
            .group_by(AICallLog.response_status)
            .all()
        )
        success = sum(r.count for r in rows if r.response_status == "success")
        error = sum(r.count for r in rows if r.response_status != "success")
        total = success + error
        rate = (success / total * 100.0) if total else None
        return {
            "success": success,
            "error": error,
            "total": total,
            "success_rate": rate,
        }

    @staticmethod
    def get_avg_latency_ms(
        year: Optional[int] = None, month: Optional[int] = None
    ) -> Optional[float]:
        """Latence moyenne (ms) sur les appels du mois ; ``None`` si vide."""
        from sqlalchemy import func, extract

        if year is None or month is None:
            now = datetime.utcnow()
            year = now.year
            month = now.month

        avg = (
            db.session.query(func.avg(AICallLog.duration_ms))
            .filter(
                AICallLog.duration_ms.isnot(None),
                extract("year", AICallLog.created_at) == year,
                extract("month", AICallLog.created_at) == month,
            )
            .scalar()
        )
        return float(avg) if avg is not None else None


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


class OpenAIPrompt(db.Model, TimestampMixin):
    """Prompts éditables depuis l'admin pour les appels OpenAI.

    Une ligne par `prompt_key` (ex. ``generate_exercises``). Les valeurs par
    défaut sont seedées au boot par ``ensure_default_prompts()`` à partir du
    dict ``_DEFAULT_PROMPTS`` défini dans ``app.services.ai_generator``.
    """

    __tablename__ = "openai_prompts"

    id = db.Column(db.Integer, primary_key=True)
    prompt_key = db.Column(db.String(80), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=True)
    system_prompt = db.Column(db.Text, nullable=False, default="")
    user_prompt_template = db.Column(db.Text, nullable=False, default="")
    available_variables = db.Column(db.Text, nullable=True)  # JSON list
    parameters_json = db.Column(db.Text, nullable=True)  # JSON dict
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    @staticmethod
    def get_or_create_default(prompt_key: str) -> Optional["OpenAIPrompt"]:
        """Retourne la ligne pour ``prompt_key`` ; la crée à partir des
        valeurs par défaut si absente. ``None`` si aucune valeur par défaut
        n'est connue pour cette clé."""
        from ..services.ai_generator import _DEFAULT_PROMPTS

        prompt = OpenAIPrompt.query.filter_by(prompt_key=prompt_key).first()
        if prompt:
            return prompt
        defaults = _DEFAULT_PROMPTS.get(prompt_key)
        if not defaults:
            return None
        prompt = OpenAIPrompt(
            prompt_key=prompt_key,
            display_name=defaults["display_name"],
            description=defaults.get("description"),
            system_prompt=defaults["system_prompt"],
            user_prompt_template=defaults["user_prompt_template"],
            available_variables=defaults.get("available_variables"),
            parameters_json=defaults.get("parameters_json"),
            is_active=True,
        )
        db.session.add(prompt)
        db.session.commit()
        return prompt

    def reset_to_default(self) -> bool:
        """Remplace les champs éditables par les valeurs par défaut.

        Retourne ``True`` si le reset a eu lieu, ``False`` si aucune valeur
        par défaut n'est définie pour ce ``prompt_key``.
        """
        from ..services.ai_generator import _DEFAULT_PROMPTS

        defaults = _DEFAULT_PROMPTS.get(self.prompt_key)
        if not defaults:
            return False
        self.display_name = defaults["display_name"]
        self.description = defaults.get("description")
        self.system_prompt = defaults["system_prompt"]
        self.user_prompt_template = defaults["user_prompt_template"]
        self.available_variables = defaults.get("available_variables")
        self.parameters_json = defaults.get("parameters_json")
        return True

    def get_parameters(self) -> dict:
        """Parse ``parameters_json`` en dict (vide si absent / invalide)."""
        import json

        if not self.parameters_json:
            return {}
        try:
            data = json.loads(self.parameters_json)
        except (ValueError, TypeError):
            return {}
        return data if isinstance(data, dict) else {}

    def get_available_variables(self) -> list:
        """Liste des variables exposées dans le template (pour l'admin)."""
        import json

        if not self.available_variables:
            return []
        try:
            data = json.loads(self.available_variables)
        except (ValueError, TypeError):
            return []
        return data if isinstance(data, list) else []

    def render_user_prompt(self, **ctx) -> str:
        """Rend ``user_prompt_template`` de façon sécurisée.

        Utilise ``_safe_format`` qui rejette tout accès attribut/index dans
        les placeholders pour prévenir l'injection SSTI. En cas d'erreur,
        retombe sur le template par défaut.
        """
        try:
            return _safe_format(self.user_prompt_template, **ctx)
        except (KeyError, IndexError, ValueError):
            from ..services.ai_generator import _DEFAULT_PROMPTS

            defaults = _DEFAULT_PROMPTS.get(self.prompt_key)
            if not defaults:
                return self.user_prompt_template
            try:
                return _safe_format(defaults["user_prompt_template"], **ctx)
            except (KeyError, IndexError, ValueError):
                return defaults["user_prompt_template"]

    def render_system_prompt(self, **ctx) -> str:
        """Rend ``system_prompt`` de façon sécurisée (fallback identique)."""
        try:
            return _safe_format(self.system_prompt, **ctx)
        except (KeyError, IndexError, ValueError):
            from ..services.ai_generator import _DEFAULT_PROMPTS

            defaults = _DEFAULT_PROMPTS.get(self.prompt_key)
            if not defaults:
                return self.system_prompt
            try:
                return _safe_format(defaults["system_prompt"], **ctx)
            except (KeyError, IndexError, ValueError):
                return defaults["system_prompt"]


class WordTranslation(db.Model, TimestampMixin):
    """Cache global des traductions de mots/expressions demandées par les élèves."""

    __tablename__ = "word_translations"

    id = db.Column(db.Integer, primary_key=True)
    word = db.Column(db.String(500), nullable=False, unique=True, index=True)
    translation = db.Column(db.Text, nullable=False)
    examples_json = db.Column(db.Text, nullable=True)

    @property
    def examples(self) -> list:
        import json as _json
        return _json.loads(self.examples_json) if self.examples_json else []


class SessionTranslationLog(db.Model, TimestampMixin):
    """Log de chaque demande de traduction effectuée pendant une session élève.

    Enregistré même pour les hits de cache (was_cached=True), contrairement
    à AICallLog qui ne trace que les vrais appels IA.
    """

    __tablename__ = "session_translation_logs"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer, db.ForeignKey("practice_sessions.id"), nullable=True, index=True
    )
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.id"), nullable=True, index=True
    )
    word = db.Column(db.String(500), nullable=False)
    translation = db.Column(db.Text, nullable=False)
    was_cached = db.Column(db.Boolean, default=False, nullable=False)
    ai_call_log_id = db.Column(
        db.Integer, db.ForeignKey("ai_call_log.id"), nullable=True
    )

    session = db.relationship("PracticeSession", backref="translation_logs")
    student = db.relationship("Student", backref="translation_logs")
