"""Helpers communs à tous les générateurs : normalisation des niveaux, pioche
dans les banques, accès aux items personnalisés en base, conjugaison du
présent simple, conversion nombres / heures en mots.
"""

import random
from typing import Dict, List, Optional, Tuple

from .base import DIFFICULTY_LEVELS, ExercisePrompt
from .pools import HOUR_WORDS, TENS_WORDS, UNITS_AND_TEENS


def normalize_difficulty(raw_value: Optional[str]) -> str:
    if not raw_value:
        return DIFFICULTY_LEVELS[0]
    value = raw_value.lower().strip()
    if value in DIFFICULTY_LEVELS:
        return value
    return DIFFICULTY_LEVELS[0]


def _custom_items(category: Optional[str], difficulty: str) -> List[ExercisePrompt]:
    try:
        from ..models import ExerciseItem, QuestionCategory
    except Exception:
        return []
    if not category:
        return []
    try:
        items = (
            ExerciseItem.query.join(QuestionCategory)
            .filter(
                QuestionCategory.code == category,
                ExerciseItem.is_active.is_(True),
                ExerciseItem.difficulty.in_([difficulty, "any"]),
            )
            .all()
        )
    except Exception:
        return []
    return [
        ExercisePrompt(prompt=item.prompt, answer=item.answer, category=category)
        for item in items
    ]


def _random_custom_item(category: Optional[str], difficulty: str) -> Optional[ExercisePrompt]:
    items = _custom_items(category, difficulty)
    if not items:
        return None
    return random.choice(items)


def _pooled_dict(data: Dict[str, Dict[str, str]], difficulty: str) -> Dict[str, str]:
    merged: Dict[str, str] = {}
    for level in DIFFICULTY_LEVELS:
        merged.update(data.get(level, {}))
        if level == difficulty:
            break
    if merged:
        return merged
    # fallback if nothing is available
    for level in DIFFICULTY_LEVELS:
        if data.get(level):
            return data[level]
    return {}


def _pooled_list(data: Dict[str, List[Tuple[str, str]]], difficulty: str) -> List[Tuple[str, str]]:
    merged: List[Tuple[str, str]] = []
    for level in DIFFICULTY_LEVELS:
        merged.extend(data.get(level, []))
        if level == difficulty:
            break
    if merged:
        return merged
    for level in DIFFICULTY_LEVELS:
        if data.get(level):
            return data[level]
    return []


def _is_third_person_singular(subject: str) -> bool:
    lowered = subject.strip().lower()
    return lowered in {"he", "she", "it"} or not any(
        lowered.startswith(token) for token in {"i", "you", "we", "they"}
    )


def _conjugate_present_simple(subject: str, base: str) -> str:
    if not _is_third_person_singular(subject):
        return base
    if base.endswith(("ch", "sh", "x", "s", "z", "o")):
        return f"{base}es"
    if base.endswith("y") and len(base) > 1 and base[-2] not in "aeiou":
        return f"{base[:-1]}ies"
    return f"{base}s"


def _number_range_for_level(difficulty: str) -> range:
    if difficulty == "beginner":
        return range(0, 51)
    if difficulty == "intermediate":
        return range(0, 201)
    return range(0, 1000)


def _number_to_words(value: int) -> str:
    if value < 20:
        return UNITS_AND_TEENS[value]
    if value < 100:
        tens, ones = divmod(value, 10)
        tens_word = TENS_WORDS[tens * 10]
        if ones:
            return f"{tens_word}-{UNITS_AND_TEENS[ones]}"
        return tens_word
    if value < 1000:
        hundreds, remainder = divmod(value, 100)
        base = f"{UNITS_AND_TEENS[hundreds]} hundred"
        if remainder:
            return f"{base} and {_number_to_words(remainder)}"
        return base
    return str(value)


def _time_to_words(hour: int, minute: int) -> str:
    hour = ((hour - 1) % 12) + 1
    hour_word = HOUR_WORDS[hour]
    if minute == 0:
        return f"{hour_word} o'clock"
    if minute == 15:
        return f"quarter past {hour_word}"
    if minute == 30:
        return f"half past {hour_word}"
    if minute == 45:
        next_hour = HOUR_WORDS[((hour) % 12) + 1]
        return f"quarter to {next_hour}"
    if minute < 30:
        minute_word = _number_to_words(minute).replace("-", " ")
        return f"{minute_word} past {hour_word}"
    next_hour = HOUR_WORDS[((hour) % 12) + 1]
    minute_word = _number_to_words(60 - minute).replace("-", " ")
    return f"{minute_word} to {next_hour}"


def _bidirectional_vocab_exercise(
    pool: Dict[str, str], category: str, theme_label_fr: str
) -> ExercisePrompt:
    """Helper : tire une paire FR/EN, choisit la direction au hasard."""
    french, english = random.choice(list(pool.items()))
    if random.random() < 0.5:
        return ExercisePrompt(
            prompt=f"Traduis en anglais ({theme_label_fr}) : « {french} »",
            answer=english,
            category=category,
        )
    return ExercisePrompt(
        prompt=f"Traduis en français ({theme_label_fr}) : « {english} »",
        answer=french,
        category=category,
    )
