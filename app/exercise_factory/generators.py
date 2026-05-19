"""Générateurs procéduraux d'exercices, un par catégorie.

Chaque fonction ``_generate_xxx(difficulty: str) -> ExercisePrompt`` est
référencée dans ``registry.py`` via un ``GeneratorSpec``. L'ajout d'un
nouveau type d'exercice se fait en trois temps :
1. Ajouter la fonction ici.
2. L'enregistrer dans ``GENERATOR_REGISTRY`` (``registry.py``).
3. Ajouter la catégorie aux seeds (``app/models/categories.py``).
"""

import random

from .base import ExercisePrompt
from .helpers import (
    _bidirectional_vocab_exercise,
    _conjugate_present_simple,
    _number_range_for_level,
    _number_to_words,
    _pooled_dict,
    _pooled_list,
    _time_to_words,
)
from .pools import (
    ADJECTIVE_OPPOSITES,
    BODY_VOCAB,
    CALENDAR_VOCAB,
    CLOTHES_VOCAB,
    CULTURE_ITEMS,
    DAILY_ROUTINE,
    FAMILY_VOCAB,
    FOOD_VOCAB,
    FR_EN_TRANSLATIONS,
    HOBBIES_VOCAB,
    INTERROGATIVE_COMPLETIONS,
    INTERROGATIVE_TRANSLATIONS,
    INTERROGATIVE_WORDS,
    PRESENT_SIMPLE_COMPLEMENTS,
    PRESENT_SIMPLE_ITEMS,
    PRESENT_SIMPLE_SUBJECTS,
    PRESENT_SIMPLE_VERBS,
    PRONOUN_ITEMS,
    SCHOOL_VOCAB,
    SENTENCE_BANK,
    THIRD_PERSON_PEOPLE,
    THIRD_PERSON_SENTENCES,
    WEATHER_VOCAB,
)


def _generate_number_word_exercise(difficulty: str) -> ExercisePrompt:
    number = random.choice(list(_number_range_for_level(difficulty)))
    return ExercisePrompt(
        prompt=f"Écris en anglais le nombre {number}.",
        answer=_number_to_words(number),
        category="number_word",
    )


def _generate_word_number_exercise(difficulty: str) -> ExercisePrompt:
    number = random.choice(list(_number_range_for_level(difficulty)))
    return ExercisePrompt(
        prompt=f"Écris en chiffres le nombre '{_number_to_words(number)}'.",
        answer=str(number),
        category="word_number",
    )


def _generate_translation_fr_en(difficulty: str) -> ExercisePrompt:
    pool = _pooled_dict(FR_EN_TRANSLATIONS, difficulty)
    french, english = random.choice(list(pool.items()))
    return ExercisePrompt(
        prompt=f"Traduis en anglais : '{french}'.",
        answer=english,
        category="translate_fr_en",
    )


def _generate_translation_en_fr(difficulty: str) -> ExercisePrompt:
    pool = _pooled_dict(FR_EN_TRANSLATIONS, difficulty)
    english, french = random.choice([(value, key) for key, value in pool.items()])
    return ExercisePrompt(
        prompt=f"Traduis en français : '{english}'.",
        answer=french,
        category="translate_en_fr",
    )


def _generate_sentence_translation(difficulty: str) -> ExercisePrompt:
    pool = _pooled_list(SENTENCE_BANK, difficulty)
    if not pool:
        return ExercisePrompt("Phrase manquante", "", "sentence_en_fr")
    english, french = random.choice(pool)
    return ExercisePrompt(
        prompt=f"Traduis en français : '{english}'.",
        answer=french,
        category="sentence_en_fr",
    )


def _generate_sentence_fr_en(difficulty: str) -> ExercisePrompt:
    pool = _pooled_list(SENTENCE_BANK, difficulty)
    if not pool:
        return ExercisePrompt("Phrase manquante", "", "sentence_fr_en")
    english, french = random.choice(pool)
    return ExercisePrompt(
        prompt=f"Traduis en anglais : '{french}'.",
        answer=english,
        category="sentence_fr_en",
    )


def _generate_time_reading_exercise(difficulty: str) -> ExercisePrompt:
    if difficulty == "beginner":
        minutes_options = [0, 15, 30]
    elif difficulty == "intermediate":
        minutes_options = [0, 15, 20, 25, 30, 35, 45]
    else:
        minutes_options = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]
    hour = random.randint(1, 12 if difficulty != "advanced" else 24)
    minute = random.choice(minutes_options)
    answer = _time_to_words(hour, minute)
    prompt_time = f"{hour:02d}:{minute:02d}"
    return ExercisePrompt(
        prompt=f"Écris en toutes lettres en anglais l'heure {prompt_time}.",
        answer=answer,
        category="time_reading",
    )


def _generate_calendar_vocabulary(difficulty: str) -> ExercisePrompt:
    pool = _pooled_dict(CALENDAR_VOCAB, difficulty)
    french, english = random.choice(list(pool.items()))
    return ExercisePrompt(
        prompt=f"Traduis en anglais : '{french}'.",
        answer=english,
        category="calendar_vocab",
    )


def _generate_family_vocabulary(difficulty: str) -> ExercisePrompt:
    pool = _pooled_dict(FAMILY_VOCAB, difficulty)
    french, english = random.choice(list(pool.items()))
    return ExercisePrompt(
        prompt=f"Comment dit-on '{french}' en anglais ?",
        answer=english,
        category="family_vocab",
    )


def _generate_school_vocabulary(difficulty: str) -> ExercisePrompt:
    pool = _pooled_dict(SCHOOL_VOCAB, difficulty)
    french, english = random.choice(list(pool.items()))
    return ExercisePrompt(
        prompt=f"Traduis ce mot de l'école en anglais : '{french}'.",
        answer=english,
        category="school_vocab",
    )


def _generate_daily_routine(difficulty: str) -> ExercisePrompt:
    pool = _pooled_dict(DAILY_ROUTINE, difficulty)
    french, english = random.choice(list(pool.items()))
    return ExercisePrompt(
        prompt=f"Traduis en anglais cette action quotidienne : '{french}'.",
        answer=english,
        category="daily_routine",
    )


def _generate_hobbies_vocabulary(difficulty: str) -> ExercisePrompt:
    pool = _pooled_dict(HOBBIES_VOCAB, difficulty)
    french, english = random.choice(list(pool.items()))
    return ExercisePrompt(
        prompt=f"Comment dit-on ce loisir en anglais : '{french}' ?",
        answer=english,
        category="hobbies_vocab",
    )


def _generate_present_simple(difficulty: str) -> ExercisePrompt:
    level_items = PRESENT_SIMPLE_ITEMS.get(difficulty) or []
    if level_items and random.random() < 0.5:
        statement, answer = random.choice(level_items)
        return ExercisePrompt(
            prompt=statement,
            answer=answer,
            category="grammar_present_simple",
        )

    subject_pool = PRESENT_SIMPLE_SUBJECTS.get(difficulty) or PRESENT_SIMPLE_SUBJECTS["beginner"]
    verb_pool = PRESENT_SIMPLE_VERBS.get(difficulty) or PRESENT_SIMPLE_VERBS["beginner"]
    complement_pool = PRESENT_SIMPLE_COMPLEMENTS.get(difficulty) or PRESENT_SIMPLE_COMPLEMENTS["beginner"]
    subject = random.choice(subject_pool)
    base_verb = random.choice(verb_pool)
    complement = random.choice(complement_pool)
    answer = _conjugate_present_simple(subject, base_verb)
    return ExercisePrompt(
        prompt=f"Complète : {subject} ___ {complement} ({base_verb}).",
        answer=answer,
        category="grammar_present_simple",
    )


def _generate_pronoun_exercise(difficulty: str) -> ExercisePrompt:
    pool = PRONOUN_ITEMS.get(difficulty) or _pooled_list(PRONOUN_ITEMS, difficulty)
    statement, answer = random.choice(pool)
    return ExercisePrompt(
        prompt=statement,
        answer=answer,
        category="grammar_pronouns",
    )


def _generate_culture_item(difficulty: str) -> ExercisePrompt:
    pool = _pooled_list(CULTURE_ITEMS, difficulty)
    statement, answer = random.choice(pool)
    return ExercisePrompt(
        prompt=statement,
        answer=answer,
        category="culture_countries",
    )


def _generate_adjective_opposite(difficulty: str) -> ExercisePrompt:
    pool = _pooled_list(ADJECTIVE_OPPOSITES, difficulty)
    statement, answer = random.choice(pool)
    return ExercisePrompt(
        prompt=statement,
        answer=answer,
        category="adjectives_opposites",
    )


def _generate_interrogative_completion(difficulty: str) -> ExercisePrompt:
    """QCM : choisir le bon mot interrogatif pour compléter la phrase."""
    pool = _pooled_list(INTERROGATIVE_COMPLETIONS, difficulty)
    sentence, answer = random.choice(pool)
    distractors = [w for w in INTERROGATIVE_WORDS if w != answer]
    options = random.sample(distractors, k=4) + [answer]
    random.shuffle(options)
    return ExercisePrompt(
        prompt=f"Complète avec le bon mot interrogatif : {sentence}",
        answer=answer,
        category="interrogative_words",
        question_type="mcq",
        options=tuple(options),
    )


def _generate_interrogative_translation(difficulty: str) -> ExercisePrompt:
    """Traduction d'une question dans un sens ou l'autre, au hasard."""
    pool = _pooled_list(INTERROGATIVE_TRANSLATIONS, difficulty)
    english, french = random.choice(pool)
    if random.random() < 0.5:
        return ExercisePrompt(
            prompt=f"Traduis en anglais : « {french} »",
            answer=english,
            category="interrogative_words",
        )
    return ExercisePrompt(
        prompt=f"Traduis en français : « {english} »",
        answer=french,
        category="interrogative_words",
    )


def _generate_food_vocabulary(difficulty: str) -> ExercisePrompt:
    return _bidirectional_vocab_exercise(
        _pooled_dict(FOOD_VOCAB, difficulty), "food_vocab", "alimentation"
    )


def _generate_body_vocabulary(difficulty: str) -> ExercisePrompt:
    return _bidirectional_vocab_exercise(
        _pooled_dict(BODY_VOCAB, difficulty), "body_vocab", "corps"
    )


def _generate_clothes_vocabulary(difficulty: str) -> ExercisePrompt:
    return _bidirectional_vocab_exercise(
        _pooled_dict(CLOTHES_VOCAB, difficulty), "clothes_vocab", "vêtements"
    )


def _generate_weather_vocabulary(difficulty: str) -> ExercisePrompt:
    return _bidirectional_vocab_exercise(
        _pooled_dict(WEATHER_VOCAB, difficulty), "weather_vocab", "météo"
    )


def _generate_third_person_s(difficulty: str) -> ExercisePrompt:
    """Réécrit une phrase en « I … » à la 3e personne du singulier.

    Ex : ``I wake up at 7`` ➜ ``Tom wakes up at 7.`` Couvre les cas
    spéciaux (go→goes, watch→watches, have→has, do→does, brush→brushes…)
    et remplace ``my`` par ``his``/``her`` selon le prénom.
    """
    pool = _pooled_list(THIRD_PERSON_SENTENCES, difficulty)
    base_verb, rest = random.choice(pool)
    name, possessive = random.choice(THIRD_PERSON_PEOPLE)
    # Verbe à particule (« wake up », « get up ») : on conjugue le 1er mot.
    head, _, particle = base_verb.partition(" ")
    if head == "have":
        head_conj = "has"
    else:
        head_conj = _conjugate_present_simple(name, head)
    conjugated = f"{head_conj} {particle}".strip()
    rest_third = " ".join(possessive if word == "my" else word for word in rest.split())
    if rest:
        original = f"I {base_verb} {rest}."
        rewritten = f"{name} {conjugated} {rest_third}."
    else:
        original = f"I {base_verb}."
        rewritten = f"{name} {conjugated}."
    return ExercisePrompt(
        prompt=f"Réécris cette phrase avec « {name} » : {original}",
        answer=rewritten,
        category="grammar_third_person_s",
    )
