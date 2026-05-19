"""Registre des générateurs et orchestration de la génération d'exercices.

``GENERATOR_REGISTRY`` lie chaque catégorie d'exercice à son builder. Les
fonctions ``generate_default_exercises`` / ``generate_exercises_for_categories``
piochent dans le registre avec dédoublonnage et fallback procédural.
"""

import random
from typing import Dict, List, Optional, Sequence, Tuple

from .base import ExercisePrompt, GeneratorSpec
from .generators import (
    _generate_adjective_opposite,
    _generate_body_vocabulary,
    _generate_calendar_vocabulary,
    _generate_clothes_vocabulary,
    _generate_culture_item,
    _generate_daily_routine,
    _generate_family_vocabulary,
    _generate_food_vocabulary,
    _generate_hobbies_vocabulary,
    _generate_interrogative_completion,
    _generate_interrogative_translation,
    _generate_number_word_exercise,
    _generate_present_simple,
    _generate_pronoun_exercise,
    _generate_school_vocabulary,
    _generate_sentence_fr_en,
    _generate_sentence_translation,
    _generate_third_person_s,
    _generate_time_reading_exercise,
    _generate_translation_en_fr,
    _generate_translation_fr_en,
    _generate_weather_vocabulary,
    _generate_word_number_exercise,
)
from .helpers import _random_custom_item, normalize_difficulty


GENERATOR_REGISTRY: List[GeneratorSpec] = [
    GeneratorSpec(("beginner", "intermediate", "advanced"), "number_word", _generate_number_word_exercise),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "word_number", _generate_word_number_exercise),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "translate_fr_en", _generate_translation_fr_en),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "translate_en_fr", _generate_translation_en_fr),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "sentence_en_fr", _generate_sentence_translation),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "sentence_fr_en", _generate_sentence_fr_en),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "time_reading", _generate_time_reading_exercise),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "calendar_vocab", _generate_calendar_vocabulary),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "family_vocab", _generate_family_vocabulary),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "school_vocab", _generate_school_vocabulary),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "daily_routine", _generate_daily_routine),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "hobbies_vocab", _generate_hobbies_vocabulary),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "grammar_present_simple", _generate_present_simple),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "grammar_pronouns", _generate_pronoun_exercise),
    GeneratorSpec(("intermediate", "advanced"), "culture_countries", _generate_culture_item),
    GeneratorSpec(("intermediate", "advanced"), "adjectives_opposites", _generate_adjective_opposite),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "interrogative_words", _generate_interrogative_completion),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "interrogative_words", _generate_interrogative_translation),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "food_vocab", _generate_food_vocabulary),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "body_vocab", _generate_body_vocabulary),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "clothes_vocab", _generate_clothes_vocabulary),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "weather_vocab", _generate_weather_vocabulary),
    GeneratorSpec(("beginner", "intermediate", "advanced"), "grammar_third_person_s", _generate_third_person_s),
]

AVAILABLE_CATEGORIES: Tuple[str, ...] = tuple(sorted({spec.category for spec in GENERATOR_REGISTRY}))


def generate_default_exercises(quantity: int = 20, difficulty: str = "beginner") -> List[ExercisePrompt]:
    normalized = normalize_difficulty(difficulty)
    exercises: List[ExercisePrompt] = []
    eligible = [spec for spec in GENERATOR_REGISTRY if normalized in spec.difficulties]
    fallback = eligible or GENERATOR_REGISTRY
    custom_categories = list({spec.category for spec in GENERATOR_REGISTRY})

    seen_signatures = set()
    attempts = 0
    max_attempts = max(10, quantity * 10)

    while len(exercises) < quantity and attempts < max_attempts:
        custom_prompt = None
        if custom_categories and random.random() < 0.35:
            custom_prompt = _random_custom_item(random.choice(custom_categories), normalized)
        if custom_prompt:
            prompt = custom_prompt
        else:
            spec = random.choice(eligible or fallback)
            prompt = spec.builder(normalized)
        signature = (prompt.category, prompt.prompt.strip().lower())
        if signature in seen_signatures:
            attempts += 1
            continue

        exercises.append(prompt)
        seen_signatures.add(signature)
        attempts = 0

    return exercises


def generate_exercises_for_categories(
    categories: Sequence[str],
    quantity: int,
    difficulty: str = "beginner",
    category_weights: Optional[Dict[str, float]] = None,
) -> List[ExercisePrompt]:
    normalized = normalize_difficulty(difficulty)
    exercises: List[ExercisePrompt] = []

    available_specs = [
        spec for spec in GENERATOR_REGISTRY
        if spec.category in categories and normalized in spec.difficulties
    ]
    if not available_specs:
        available_specs = [spec for spec in GENERATOR_REGISTRY if spec.category in categories]
    if not available_specs:
        return generate_default_exercises(quantity, difficulty=normalized)

    specs_by_category: Dict[str, List[GeneratorSpec]] = {}
    for spec in available_specs:
        specs_by_category.setdefault(spec.category, []).append(spec)

    weighted_categories = list(specs_by_category.keys())
    weights = []
    for category in weighted_categories:
        weight = 1.0
        if category_weights:
            weight = max(0.1, float(category_weights.get(category, 1.0)))
        weights.append(weight)

    seen_signatures = set()
    attempts = 0
    max_attempts = max(10, quantity * 12)

    while len(exercises) < quantity and attempts < max_attempts:
        selected_category = random.choices(weighted_categories, weights=weights, k=1)[0]
        custom_prompt = _random_custom_item(selected_category, normalized)
        if custom_prompt and random.random() < 0.7:
            prompt = custom_prompt
        else:
            spec = random.choice(specs_by_category[selected_category])
            prompt = spec.builder(normalized)
        signature = (prompt.category, prompt.prompt.strip().lower())
        if signature in seen_signatures:
            attempts += 1
            continue
        exercises.append(prompt)
        seen_signatures.add(signature)
        attempts = 0

    if len(exercises) < quantity:
        exercises.extend(generate_default_exercises(quantity - len(exercises), difficulty=normalized))

    return exercises
