"""Types et constantes partagés par tous les générateurs d'exercices."""

from dataclasses import dataclass, field
from typing import Callable, Dict, Sequence, Tuple


@dataclass(frozen=True)
class ExercisePrompt:
    """Représente un exercice prêt à être joué.

    Les champs ``question_type``, ``options`` et ``accepted_answers`` sont
    optionnels pour rester rétro-compatibles avec les générateurs historiques
    qui produisent uniquement des questions textuelles.

    - ``question_type='text'`` : saisie libre (défaut).
    - ``question_type='mcq'`` : l'élève doit choisir une valeur exacte de
      ``options``. ``answer`` doit aussi figurer dans ``options``.
    - ``question_type='word_bank'`` : saisie libre, mais ``options`` est
      affichée comme banque de mots à piocher.

    ``accepted_answers`` liste les variantes acceptées en plus de ``answer``
    (utile pour les traductions à plusieurs formulations valides).
    """

    prompt: str
    answer: str
    category: str
    question_type: str = "text"
    options: Tuple[str, ...] = field(default_factory=tuple)
    accepted_answers: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class GeneratorSpec:
    difficulties: Sequence[str]
    category: str
    builder: Callable[[str], ExercisePrompt]


DIFFICULTY_LEVELS: Tuple[str, ...] = ("beginner", "intermediate", "advanced")
DIFFICULTY_LABELS: Dict[str, str] = {
    "beginner": "Débutant",
    "intermediate": "Intermédiaire",
    "advanced": "Avancé",
}
