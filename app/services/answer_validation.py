"""Moteur de correction des réponses élèves.

Encapsule la normalisation (espaces, casse, apostrophes typographiques,
optionnellement diacritiques), la tolérance aux articles ("a dress"
↔ "dress"), la détection de blank dans un énoncé pour autoriser la
réponse en mode "contains", et l'agrégation des variantes acceptées
stockées en JSON sur ``SessionExercise.accepted_answers_json``.

Fonctions pures : pas d'accès à ``g`` / ``session`` / ``db``.
"""

import json
import re
from typing import List, Optional

from ..exercise_factory import ExercisePrompt
from ..models import SessionExercise


_ARTICLE_RE = re.compile(r"^(?:a|an|the)\s+")


def _normalize_answer(value: str, loose: bool = False) -> str:
    normalized = value.strip().lower()
    normalized = normalized.replace("’", "'").replace("‘", "'").replace("`", "'")
    normalized = " ".join(normalized.split())
    if not loose:
        return normalized
    import unicodedata

    normalized = unicodedata.normalize("NFKD", normalized)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return normalized


def _strip_article(text: str) -> str:
    return _ARTICLE_RE.sub("", text)


def _prompt_has_blank(prompt: str) -> bool:
    if not prompt:
        return False
    return bool(re.search(r"_{3,}|\\.{3,}|…", prompt))


def _accepted_answers(exercise: SessionExercise) -> List[str]:
    """Liste des réponses acceptées : `correct_answer` + variantes JSON."""
    answers: List[str] = []
    if exercise.correct_answer:
        answers.append(exercise.correct_answer)
    raw = getattr(exercise, "accepted_answers_json", None)
    if raw:
        try:
            extra = json.loads(raw)
            if isinstance(extra, list):
                answers.extend(str(item) for item in extra if item)
        except (ValueError, TypeError):
            pass
    return answers


def _is_answer_correct(exercise: SessionExercise) -> bool:
    user_answer = exercise.student_answer or ""
    candidates = _accepted_answers(exercise)
    if not candidates:
        return False

    strict_actual = _normalize_answer(user_answer, loose=False)
    question_type = getattr(exercise, "question_type", "text") or "text"

    # QCM : l'élève a cliqué un bouton, on exige le match exact (case/espaces).
    if question_type == "mcq":
        return any(
            strict_actual == _normalize_answer(answer, loose=False)
            for answer in candidates
        )

    translation_categories = {
        "translate_en_fr",
        "translate_fr_en",
        "sentence_en_fr",
        "sentence_fr_en",
        "interrogative_words",
    }
    loose_eligible = exercise.category in translation_categories
    loose_actual = _normalize_answer(user_answer, loose=True) if loose_eligible else None

    has_blank = _prompt_has_blank(exercise.prompt)

    for answer in candidates:
        strict_expected = _normalize_answer(answer, loose=False)
        if strict_expected == strict_actual:
            return True
        if loose_eligible:
            if _normalize_answer(answer, loose=True) == loose_actual:
                return True
        if has_blank:
            pattern = rf"\b{re.escape(strict_expected)}\b"
            if re.search(pattern, strict_actual):
                return True

    # Tolérance articles : "a dress" ≅ "dress", "an apple" ≅ "apple"
    if question_type != "mcq":
        stripped_actual = _strip_article(strict_actual)
        if stripped_actual:
            for answer in candidates:
                stripped_expected = _strip_article(_normalize_answer(answer, loose=False))
                if stripped_actual == stripped_expected:
                    return True
                if loose_eligible and loose_actual is not None:
                    if _strip_article(loose_actual) == _strip_article(
                        _normalize_answer(answer, loose=True)
                    ):
                        return True

    return False


def _session_exercise_kwargs(
    prompt: ExercisePrompt,
    *,
    source: str = "procedural",
    ai_exercise_id: Optional[int] = None,
) -> dict:
    """Convertit un ``ExercisePrompt`` en kwargs pour ``SessionExercise(...)``."""
    return {
        "prompt": prompt.prompt,
        "correct_answer": prompt.answer,
        "category": prompt.category,
        "question_type": prompt.question_type,
        "options_json": json.dumps(list(prompt.options)) if prompt.options else None,
        "accepted_answers_json": (
            json.dumps(list(prompt.accepted_answers))
            if prompt.accepted_answers
            else None
        ),
        "source": source,
        "ai_exercise_id": ai_exercise_id,
    }
