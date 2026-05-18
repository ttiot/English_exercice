"""Package de génération procédurale d'exercices.

API publique stable (ré-exportée pour ``app.routes`` et autres consommateurs) :
- ``ExercisePrompt`` / ``GeneratorSpec`` : structures de données
- ``DIFFICULTY_LEVELS`` / ``DIFFICULTY_LABELS`` : constantes
- ``normalize_difficulty`` : helper de validation des niveaux
- ``AVAILABLE_CATEGORIES`` : tuple trié des catégories supportées
- ``generate_default_exercises`` / ``generate_exercises_for_categories`` :
  fonctions d'orchestration
"""

from .base import (
    DIFFICULTY_LABELS,
    DIFFICULTY_LEVELS,
    ExercisePrompt,
    GeneratorSpec,
)
from .helpers import normalize_difficulty
from .registry import (
    AVAILABLE_CATEGORIES,
    GENERATOR_REGISTRY,
    generate_default_exercises,
    generate_exercises_for_categories,
)


__all__ = [
    "AVAILABLE_CATEGORIES",
    "DIFFICULTY_LABELS",
    "DIFFICULTY_LEVELS",
    "ExercisePrompt",
    "GENERATOR_REGISTRY",
    "GeneratorSpec",
    "generate_default_exercises",
    "generate_exercises_for_categories",
    "normalize_difficulty",
]
