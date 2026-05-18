"""Package des modèles SQLAlchemy.

Le module ``app.models`` reste une API publique stable : tout ce qui était
exposé par l'ancien ``app/models.py`` est ré-exporté ici pour ne pas casser
les imports existants (``from app.models import Student``, etc.).

L'ordre des imports importe : les modules qui définissent des classes
référencées par d'autres via ``db.relationship("...")`` n'ont pas besoin
d'être importés en premier (SQLAlchemy résout les chaînes paresseusement),
mais TOUS doivent être importés avant la première requête — c'est le rôle
de ce ``__init__.py``.
"""

from .ai import (
    AICallLog,
    AIGeneratedExercise,
    OpenAIConfig,
    OpenAIPrompt,
    SessionTranslationLog,
    WordTranslation,
)
from .app_settings import AppConfig, EmailConfig
from .categories import (
    DEFAULT_CATEGORY_METADATA,
    DEFAULT_CATEGORY_NAMES,
    QuestionCategory,
    SkillPrerequisite,
)
from .core import Student, TimestampMixin, parent_student
from .exercises import (
    ExerciseItem,
    PracticeSession,
    PreparedExercise,
    PreparedExerciseQuestion,
    PreparedExerciseSet,
    SessionExercise,
)
from .migrations import ensure_schema_migrations
from .progression import (
    Badge,
    ReviewPlan,
    StudentBadge,
    StudentSkillProgress,
    WeeklyGoal,
)
from .seed import (
    ensure_admin_account,
    ensure_default_badges,
    ensure_default_categories,
    ensure_default_prerequisites,
    ensure_default_prompts,
)
from .utils import _safe_format


__all__ = [
    # Mixin & utils
    "TimestampMixin",
    "_safe_format",
    "parent_student",
    # Core
    "Student",
    # Categories
    "QuestionCategory",
    "SkillPrerequisite",
    "DEFAULT_CATEGORY_NAMES",
    "DEFAULT_CATEGORY_METADATA",
    # Exercises
    "PracticeSession",
    "SessionExercise",
    "PreparedExercise",
    "PreparedExerciseSet",
    "PreparedExerciseQuestion",
    "ExerciseItem",
    # Progression
    "WeeklyGoal",
    "Badge",
    "StudentBadge",
    "ReviewPlan",
    "StudentSkillProgress",
    # AI
    "OpenAIConfig",
    "AICallLog",
    "AIGeneratedExercise",
    "OpenAIPrompt",
    "WordTranslation",
    "SessionTranslationLog",
    # App settings
    "AppConfig",
    "EmailConfig",
    # Seed / migrations
    "ensure_default_badges",
    "ensure_default_categories",
    "ensure_default_prompts",
    "ensure_default_prerequisites",
    "ensure_schema_migrations",
    "ensure_admin_account",
]
