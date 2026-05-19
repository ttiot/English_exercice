"""Modèles liés à l'IA : config OpenAI, prompts éditables, logs d'appels,
exercices générés et cache de traductions.
"""

from datetime import datetime
from typing import Optional

from ..extensions import db
from .core import TimestampMixin
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

    # NB : la logique d'aggrégation (coût, stats mensuelles, trend, top
    # élèves, etc.) vit dans ``app.services.ai_analytics``. Le modèle reste
    # un conteneur ORM pur ; le service est testable sans contexte Flask.


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
