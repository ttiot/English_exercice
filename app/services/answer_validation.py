"""Moteur de correction des réponses élèves.

Encapsule la normalisation (espaces, casse, apostrophes typographiques,
optionnellement diacritiques), la tolérance aux articles ("a dress"
↔ "dress"), la détection de blank dans un énoncé pour autoriser la
réponse en mode "contains", et l'agrégation des variantes acceptées
stockées en JSON sur ``SessionExercise.accepted_answers_json``.

Statuts de correction :
- ``'correct'``   : réponse exacte (ou variante acceptée).
- ``'near_miss'`` : faute d'orthographe isolée (distance Levenshtein = 1),
                   la réponse est acceptée avec un avertissement.
- ``'incorrect'`` : réponse fausse.

Fonctions pures : pas d'accès à ``g`` / ``session`` / ``db``.
"""

import json
import re
import unicodedata
from typing import List, Optional, Tuple

from ..exercise_factory import ExercisePrompt
from ..models import SessionExercise


_ARTICLE_RE = re.compile(r"^(?:a|an|the)\s+")

# Formes contractées → développées (toutes en minuscules, apostrophe droite)
_CONTRACTIONS: dict = {
    "don't": "do not",
    "doesn't": "does not",
    "didn't": "did not",
    "isn't": "is not",
    "aren't": "are not",
    "wasn't": "was not",
    "weren't": "were not",
    "can't": "cannot",
    "couldn't": "could not",
    "won't": "will not",
    "wouldn't": "would not",
    "haven't": "have not",
    "hasn't": "has not",
    "hadn't": "had not",
    "i'm": "i am",
    "you're": "you are",
    "he's": "he is",
    "she's": "she is",
    "it's": "it is",
    "we're": "we are",
    "they're": "they are",
    "i've": "i have",
    "you've": "you have",
    "we've": "we have",
    "they've": "they have",
    "i'd": "i would",
    "you'd": "you would",
    "he'd": "he would",
    "she'd": "she would",
    "we'd": "we would",
    "they'd": "they would",
    "i'll": "i will",
    "you'll": "you will",
    "he'll": "he will",
    "she'll": "she will",
    "we'll": "we will",
    "they'll": "they will",
}
# Index inverse : forme développée → contractée
_EXPANSIONS: dict = {v: k for k, v in _CONTRACTIONS.items()}


def _normalize_answer(value: str, loose: bool = False) -> str:
    normalized = value.strip().lower()
    # Normalisation des apostrophes (iOS, Android, claviers variés…)
    normalized = normalized.replace("’", "'").replace("‘", "'").replace("`", "'")
    # Suppression des espaces multiples (correction automatique mobile)
    normalized = " ".join(normalized.split())
    # Suppression du point final non sémantique
    normalized = normalized.rstrip(".!?")
    if not loose:
        return normalized
    normalized = unicodedata.normalize("NFKD", normalized)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return normalized


def _expand_contractions(text: str) -> str:
    """Développe les contractions : "don't" → "do not"."""
    words = text.split()
    return " ".join(_CONTRACTIONS.get(w, w) for w in words)


def _contract_expansions(text: str) -> str:
    """Contracte les formes développées : "do not" → "don't"."""
    # Remplacement mot-à-mot sur les bigrammes et trigrammes
    for expanded, contracted in _EXPANSIONS.items():
        text = re.sub(r"\b" + re.escape(expanded) + r"\b", contracted, text)
    return text


def _contraction_variants(text: str) -> List[str]:
    """Renvoie les variantes contractée et développée d'un texte normalisé."""
    variants = [text]
    expanded = _expand_contractions(text)
    if expanded != text:
        variants.append(expanded)
    contracted = _contract_expansions(text)
    if contracted != text:
        variants.append(contracted)
    return variants


def _strip_article(text: str) -> str:
    return _ARTICLE_RE.sub("", text)


def _prompt_has_blank(prompt: str) -> bool:
    if not prompt:
        return False
    return bool(re.search(r"_{3,}|\\.{3,}|…", prompt))


def _levenshtein(a: str, b: str) -> int:
    """Distance de Levenshtein entre deux chaînes (insertion/suppression/substitution)."""
    if a == b:
        return 0
    len_a, len_b = len(a), len(b)
    if len_a == 0:
        return len_b
    if len_b == 0:
        return len_a
    # Optimisation : une seule ligne de DP
    prev = list(range(len_b + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len_b
        for j, cb in enumerate(b, 1):
            curr[j] = min(
                prev[j] + 1,          # suppression
                curr[j - 1] + 1,      # insertion
                prev[j - 1] + (0 if ca == cb else 1),  # substitution
            )
        prev = curr
    return prev[len_b]


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


def _check_answer_status(exercise: SessionExercise) -> Tuple[str, Optional[str]]:
    """Renvoie ``(statut, meilleure_réponse_attendue)`` où statut ∈ {correct, near_miss, incorrect}.

    ``meilleure_réponse_attendue`` est la réponse candidate la plus proche
    (utile pour afficher l'orthographe correcte en cas de near_miss).
    """
    user_answer = exercise.student_answer or ""
    candidates = _accepted_answers(exercise)
    if not candidates:
        return "incorrect", None

    question_type = getattr(exercise, "question_type", "text") or "text"
    strict_actual = _normalize_answer(user_answer, loose=False)

    # ── QCM : correspondance stricte uniquement ──────────────────────────────
    if question_type == "mcq":
        for answer in candidates:
            if strict_actual == _normalize_answer(answer, loose=False):
                return "correct", answer
        return "incorrect", candidates[0]

    # ── Exercices textuels / word_bank ───────────────────────────────────────
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

    # Variantes avec contractions (développé ↔ contracté)
    actual_variants = _contraction_variants(strict_actual)
    if loose_eligible and loose_actual is not None:
        actual_loose_variants = _contraction_variants(loose_actual)
    else:
        actual_loose_variants = []

    # ── Correspondance exacte ────────────────────────────────────────────────
    for answer in candidates:
        strict_expected = _normalize_answer(answer, loose=False)
        expected_variants = _contraction_variants(strict_expected)

        # Correspondance directe ou avec contractions
        for av in actual_variants:
            if av in expected_variants:
                return "correct", answer

        # Correspondance loose (diacritiques) avec contractions
        if loose_eligible and loose_actual is not None:
            loose_expected = _normalize_answer(answer, loose=True)
            loose_expected_variants = _contraction_variants(loose_expected)
            for av in actual_loose_variants:
                if av in loose_expected_variants:
                    return "correct", answer

        # Correspondance dans un énoncé à trou
        if has_blank:
            pattern = rf"\b{re.escape(strict_expected)}\b"
            if re.search(pattern, strict_actual):
                return "correct", answer

    # Tolérance articles : "a dress" ≅ "dress"
    if question_type != "mcq":
        stripped_actual = _strip_article(strict_actual)
        if stripped_actual:
            for answer in candidates:
                stripped_expected = _strip_article(_normalize_answer(answer, loose=False))
                if stripped_actual == stripped_expected:
                    return "correct", answer
                if loose_eligible and loose_actual is not None:
                    if _strip_article(loose_actual) == _strip_article(
                        _normalize_answer(answer, loose=True)
                    ):
                        return "correct", answer

    # ── Near-miss (Levenshtein = 1, exercices textuels non-à-trou) ──────────
    if not has_blank and question_type != "mcq":
        best_dist = None
        best_candidate = None
        for answer in candidates:
            norm_expected = _normalize_answer(answer, loose=False)
            for av in actual_variants:
                d = _levenshtein(av, norm_expected)
                if best_dist is None or d < best_dist:
                    best_dist = d
                    best_candidate = answer
            if loose_eligible and loose_actual is not None:
                norm_expected_loose = _normalize_answer(answer, loose=True)
                for av in actual_loose_variants:
                    d = _levenshtein(av, norm_expected_loose)
                    if best_dist is None or d < best_dist:
                        best_dist = d
                        best_candidate = answer
        if best_dist == 1:
            return "near_miss", best_candidate

    return "incorrect", candidates[0] if candidates else None


def _is_answer_correct(exercise: SessionExercise) -> bool:
    """Rétro-compatibilité : True si correct ou near_miss."""
    status, _ = _check_answer_status(exercise)
    return status != "incorrect"


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
        "explanation": getattr(prompt, "explanation", None) or None,
        "source": source,
        "ai_exercise_id": ai_exercise_id,
    }
