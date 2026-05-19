import json
import pytest

# ==========================================
# 1. MOCKS ET IMPORTS
# ==========================================

from app.services.answer_validation import (
    _normalize_answer,
    _expand_contractions,
    _contract_expansions,
    _strip_french_det,
    _levenshtein,
    _check_answer_status,
)


# Simule le modèle SQLAlchemy/Base de données pour les tests
class SessionExerciseMock:
    def __init__(self, student_answer="", correct_answer="", accepted_answers_json=None, category="text", question_type="text", prompt=""):
        self.student_answer = student_answer
        self.correct_answer = correct_answer
        self.accepted_answers_json = accepted_answers_json
        self.category = category
        self.question_type = question_type
        self.prompt = prompt


# ==========================================
# 2. TESTS UNITAIRES DES FONCTIONS PURES
# ==========================================

@pytest.mark.parametrize("input_str, expected_strict, expected_loose", [
    ("  Hello   World!?!  ", "hello world", "hello world"),
    ("It's a `test'.", "it's a 'test'", "it's a 'test'"),
    ("garçon", "garçon", "garcon"),
    ("Hôtel", "hôtel", "hotel"),
])
def test_normalize_answer(input_str, expected_strict, expected_loose):
    # Test strict (sans retrait des diacritiques)
    assert _normalize_answer(input_str, loose=False) == expected_strict
    # Test loose (avec retrait des diacritiques)
    assert _normalize_answer(input_str, loose=True) == expected_loose


@pytest.mark.parametrize("input_str, expected", [
    ("i don't know", "i do not know"),
    ("she isn't here", "she is not here"),
    ("they're happy", "they are happy"),
    ("normal text", "normal text")
])
def test_expand_contractions(input_str, expected):
    assert _expand_contractions(input_str) == expected


@pytest.mark.parametrize("input_str, expected", [
    ("i do not know", "i don't know"),
    ("she is not here", "she isn't here"),
    ("they are happy", "they're happy"),
    ("we are not sure", "we aren't sure"), # Note: selon votre dict "we are" -> "we're", mais géré par le bigramme
])
def test_contract_expansions(input_str, expected):
    # Ce test pourrait révéler des conflits si "we are not" devient "we're not" ou "we aren't".
    # Il teste votre logique actuelle de remplacement.
    assert _contract_expansions(input_str) == expected


@pytest.mark.parametrize("input_str, expected", [
    ("le chat", "chat"),
    ("une maison", "maison"),
    ("de la confiture", "confiture"),
    ("l' avion", "avion"),
    # Attention: Si vous n'avez pas mis à jour votre Regex (avec \s* et d'),
    # les deux tests suivants échoueront. C'est le but du Test-Driven Development !
    ("l'avion", "avion"),
    ("d'argent", "argent"),
])
def test_strip_french_det(input_str, expected):
    assert _strip_french_det(input_str) == expected


@pytest.mark.parametrize("a, b, expected_dist", [
    ("chat", "chat", 0),
    ("chat", "cat", 1),       # Suppression
    ("chat", "chart", 1),     # Insertion
    ("chat", "cjat", 1),      # Substitution
    ("understanding", "understanidng", 2), # Inversion de 2 lettres = 2 substitutions
])
def test_levenshtein(a, b, expected_dist):
    assert _levenshtein(a, b) == expected_dist


# ==========================================
# 3. TESTS D'INTÉGRATION DU STATUT
# ==========================================

def test_check_answer_status_exact_match():
    ex = SessionExerciseMock(
        student_answer="A beautiful dress!",
        correct_answer="a beautiful dress",
    )
    status, best_ans = _check_answer_status(ex)
    assert status == "correct"


def test_check_answer_status_mcq_strictness():
    # Pour un QCM, la tolérance sur les articles ne doit PAS s'appliquer
    ex = SessionExerciseMock(
        student_answer="dress",
        correct_answer="a dress",
        question_type="mcq"
    )
    status, best_ans = _check_answer_status(ex)
    assert status == "incorrect"


def test_check_answer_status_article_tolerance():
    # Tolérance de l'article anglais : "dress" = "a dress"
    ex = SessionExerciseMock(
        student_answer="dress",
        correct_answer="a dress",
        question_type="text"
    )
    status, best_ans = _check_answer_status(ex)
    assert status == "correct"


def test_check_answer_status_contractions():
    # L'élève écrit contracté, l'attendu est développé
    ex = SessionExerciseMock(
        student_answer="I don't care.",
        correct_answer="I do not care",
        category="translate_en_fr"
    )
    status, best_ans = _check_answer_status(ex)
    assert status == "correct"

    # L'élève écrit développé, l'attendu est contracté
    ex2 = SessionExerciseMock(
        student_answer="She is not here",
        correct_answer="she isn't here"
    )
    status2, best_ans2 = _check_answer_status(ex2)
    assert status2 == "correct"


def test_check_answer_status_article_missing_french():
    # Test de l'oubli du déterminant français (doit renvoyer article_missing)
    ex = SessionExerciseMock(
        student_answer="pomme",
        correct_answer="la pomme",
        category="translate_en_fr" # Catégorie éligible pour le français
    )
    status, best_ans = _check_answer_status(ex)
    assert status == "article_missing"


def test_check_answer_status_near_miss():
    # Test de la faute de frappe (Levenshtein = 1)
    ex = SessionExerciseMock(
        student_answer="conputer", # 'n' au lieu de 'm'
        correct_answer="computer",
        question_type="text"
    )
    status, best_ans = _check_answer_status(ex)
    assert status == "near_miss"


def test_check_answer_status_blank_contains():
    # L'élève tape toute la phrase alors qu'il y a un trou
    ex = SessionExerciseMock(
        student_answer="I went to the store",
        correct_answer="went",
        prompt="I ___ to the store." # Contient un "blank" détectable
    )
    status, best_ans = _check_answer_status(ex)
    assert status == "correct"


def test_check_answer_status_multiple_accepted_answers():
    # Test du JSON d'alternatives
    accepted = json.dumps(["he went", "he has gone"])
    ex = SessionExerciseMock(
        student_answer="He has gone!",
        correct_answer="he left",
        accepted_answers_json=accepted
    )
    status, best_ans = _check_answer_status(ex)
    assert status == "correct"
    assert best_ans == "he has gone" # Il doit retourner la variante exacte matchée
