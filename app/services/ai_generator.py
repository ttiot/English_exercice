"""Service de génération d'exercices via l'API OpenAI.

Pipeline :

1. ``get_openai_client()`` résout la clé API (BDD via ``OpenAIConfig`` puis
   variable d'env ``OPENAI_API_KEY``) et renvoie un client OpenAI prêt.
2. ``generate_exercises()`` appelle la *Responses API* avec un JSON schema
   strict (cf. :data:`EXERCISE_BATCH_SCHEMA`), parse le résultat, persiste
   chaque exercice dans le pool ``AIGeneratedExercise`` puis renvoie une
   liste d'``ExercisePrompt`` consommable par le moteur de session.
3. ``test_connection()`` vérifie qu'une clé est valide en listant les
   modèles ; utilisé par le bouton « Tester » de la page admin.

Tous les appels sont audités dans ``AICallLog`` (tokens, coût, durée).
"""
from __future__ import annotations

import json
import logging
import time
from typing import List, Optional, Tuple

from .. import db
from ..exercise_factory import AVAILABLE_CATEGORIES, ExercisePrompt
from ..models import AIGeneratedExercise, OpenAIConfig, OpenAIPrompt
from . import ai_analytics

logger = logging.getLogger(__name__)


# Catégories autorisées pour les exos IA. On ajoute "ai_generated" comme
# fallback générique au cas où l'IA s'écarterait des thèmes existants.
_ALLOWED_CATEGORIES: Tuple[str, ...] = AVAILABLE_CATEGORIES + ("ai_generated",)
_ALLOWED_QUESTION_TYPES: Tuple[str, ...] = ("text", "mcq", "word_bank")
_ALLOWED_DIFFICULTIES: Tuple[str, ...] = ("beginner", "intermediate", "advanced")


# JSON Schema strict (compatible OpenAI Structured Outputs).
EXERCISE_BATCH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["exercises"],
    "properties": {
        "exercises": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "prompt",
                    "answer",
                    "category",
                    "question_type",
                    "options",
                    "accepted_answers",
                ],
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": (
                            "Énoncé de la question, en français. Les mots "
                            "anglais peuvent être inclus entre guillemets."
                        ),
                    },
                    "answer": {
                        "type": "string",
                        "description": (
                            "Réponse attendue exacte. "
                            "Pour translate_fr_en/sentence_fr_en : traduction anglaise de la phrase donnée. "
                            "Pour translate_en_fr/sentence_en_fr : traduction française de la phrase donnée. "
                            "Pour les autres catégories : réponse en anglais."
                        ),
                    },
                    "category": {
                        "type": "string",
                        "enum": list(_ALLOWED_CATEGORIES),
                    },
                    "question_type": {
                        "type": "string",
                        "enum": list(_ALLOWED_QUESTION_TYPES),
                    },
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Choix pour question_type=mcq (inclure la bonne "
                            "réponse). Banque de mots pour word_bank. Tableau "
                            "vide [] pour text."
                        ),
                    },
                    "accepted_answers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Variantes acceptées en plus de `answer` (ex. "
                            "synonymes, formulations alternatives). [] si "
                            "aucune."
                        ),
                    },
                },
            },
        }
    },
}


_SYSTEM_PROMPT_TEMPLATE = """Tu es un professeur d'anglais qui prépare des \
exercices pour un élève français de 6ème (CECRL A1-A2). Tu dois répondre \
EXCLUSIVEMENT par un JSON conforme au schéma fourni.

Règles à respecter :
- Les énoncés ("prompt") sont rédigés en français. Les mots ou phrases en \
anglais à manipuler peuvent y figurer entre guillemets.
- Pour `translate_fr_en` et `sentence_fr_en` : l'énoncé ("prompt") contient \
uniquement la phrase française à traduire, au format \
"Traduis en anglais : '...'". La réponse ("answer") est obligatoirement la \
traduction anglaise. Ne jamais inclure la traduction dans l'énoncé.
- Pour `translate_en_fr` et `sentence_en_fr` : l'énoncé ("prompt") contient \
uniquement la phrase anglaise à traduire, au format \
"Traduis en français : '...'". La réponse ("answer") est obligatoirement la \
traduction française. Ne jamais inclure la traduction dans l'énoncé.
- Pour toutes les autres catégories : la réponse ("answer") est en anglais.
- Vocabulaire et grammaire adaptés au niveau {difficulty}.
- Pour `question_type='mcq'` : 4 ou 5 options dont la bonne réponse, qui \
doit aussi figurer dans `options`.
- Pour `question_type='word_bank'` : ~6 mots dont la bonne réponse, l'élève \
saisira sa réponse en s'aidant de la banque.
- Pour `question_type='text'` : `options` doit être [].
- Choisir `category` parmi celles fournies. Utiliser `ai_generated` \
seulement si aucune catégorie ne convient.
- Toujours inclure `accepted_answers` (peut être []), notamment pour les \
traductions où plusieurs formulations sont valides.
- Pas d'emoji, pas de markdown, pas de commentaire en dehors du JSON.

Catégories disponibles : {categories}.
"""


_USER_PROMPT_TEMPLATE = (
    "Génère exactement {count} exercices d'anglais sur le thème suivant, "
    "en respectant le niveau {difficulty} :\n\n"
    "« {student_prompt} »\n\n"
    "Varie les `question_type` et les `category` quand c'est cohérent avec "
    "le thème. Donne un mélange équilibré de types (texte / mcq / "
    "word_bank) si le thème s'y prête."
)


_SYSTEM_PROMPT_TRANSLATION = (
    "Tu es un assistant pédagogique pour des collégiens français (6ème/5ème) "
    "qui apprennent l'anglais. Quand on te donne un mot ou une expression, "
    "détecte sa langue, traduis-le dans l'autre langue (anglais ↔ français) "
    "et donne 2 exemples d'utilisation simples adaptés au niveau collège, "
    "chacun suivi de sa traduction entre parenthèses. "
    "Réponds uniquement avec le JSON demandé, sans commentaire."
)

# Prompts par défaut seedés en BDD au boot par ``ensure_default_prompts()``.
# Si un admin édite le prompt côté UI, c'est la version BDD qui prime ;
# les valeurs ci-dessous ne servent plus que de fallback (KeyError, reset).
_DEFAULT_PROMPTS: dict = {
    "generate_exercises": {
        "display_name": "Génération d'exercices",
        "description": (
            "Prompt utilisé par les sessions « Sur mesure (IA) » pour générer "
            "des exercices d'anglais à partir d'un thème saisi par l'élève. "
            "La sortie doit être un JSON conforme au schéma `exercise_batch`."
        ),
        "system_prompt": _SYSTEM_PROMPT_TEMPLATE,
        "user_prompt_template": _USER_PROMPT_TEMPLATE,
        "available_variables": json.dumps(
            ["difficulty", "categories", "student_prompt", "count"]
        ),
        "parameters_json": json.dumps({"max_output_tokens": 2000}),
    },
    "word_translation": {
        "display_name": "Traduction de mots",
        "description": (
            "Prompt utilisé lors des sessions d'exercices quand un élève sélectionne "
            "un mot pour obtenir une traduction instantanée. "
            "La sortie doit être un JSON avec les champs `translation` et `examples`."
        ),
        "system_prompt": _SYSTEM_PROMPT_TRANSLATION,
        "user_prompt_template": 'Traduis : "{word}"\nContexte : « {context} »',
        "available_variables": json.dumps(["word", "context"]),
        "parameters_json": json.dumps({"max_output_tokens": 300}),
    },
}


def get_openai_client() -> Tuple[Optional[object], dict]:
    """Construit un client OpenAI selon la priorité : BDD → env.

    Renvoie ``(client_or_None, info)`` avec ``info`` qui contient au moins
    ``model``, ``base_url`` et ``source`` (``'global'`` / ``'env'`` / ``'none'``).
    Le client peut être ``None`` si aucune clé n'est résolvable.
    """
    from flask import current_app

    info = {"model": None, "base_url": None, "source": "none"}

    try:
        from openai import OpenAI
    except ImportError:
        logger.error("La librairie openai n'est pas installée.")
        return None, info

    config = OpenAIConfig.get_active()
    if config:
        api_key = config.get_api_key()
        if api_key:
            info["model"] = config.default_model or "gpt-4o-mini"
            info["base_url"] = (
                config.base_url or "https://api.openai.com/v1"
            ).rstrip("/")
            info["source"] = "global"
            try:
                client = OpenAI(api_key=api_key, base_url=info["base_url"])
                return client, info
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Impossible d'instancier le client OpenAI (BDD) : %s", exc
                )

    env_key = (current_app.config.get("OPENAI_API_KEY") or "").strip()
    if env_key:
        info["model"] = current_app.config.get("OPENAI_MODEL") or "gpt-4o-mini"
        info["base_url"] = (
            current_app.config.get("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        ).rstrip("/")
        info["source"] = "env"
        try:
            client = OpenAI(api_key=env_key, base_url=info["base_url"])
            return client, info
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Impossible d'instancier le client OpenAI (env) : %s", exc
            )

    return None, info


def is_budget_exceeded() -> bool:
    """``True`` si un budget mensuel est défini et déjà dépassé."""
    config = OpenAIConfig.get_active()
    if not config or not config.monthly_budget_usd:
        return False
    spent = ai_analytics.get_monthly_cost_usd()
    return spent >= config.monthly_budget_usd


def test_connection() -> dict:
    """Tente un ``client.models.list()`` pour valider la clé courante."""
    client, info = get_openai_client()
    if not client:
        return {"success": False, "error": "Aucune clé API OpenAI configurée."}
    try:
        response = client.models.list()
        models = [m.id for m in list(response)[:10]]
        return {
            "success": True,
            "source": info["source"],
            "default_model": info["model"],
            "available_models": models,
        }
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": str(exc)}


def _extract_token_usage(response) -> Tuple[Optional[int], Optional[int]]:
    usage = getattr(response, "usage", None)
    if not usage:
        return None, None
    input_tokens = (
        getattr(usage, "input_tokens", None)
        or getattr(usage, "prompt_tokens", None)
    )
    output_tokens = (
        getattr(usage, "output_tokens", None)
        or getattr(usage, "completion_tokens", None)
    )
    return input_tokens, output_tokens


def _coerce_exercise(raw: dict) -> Optional[ExercisePrompt]:
    """Valide un exo IA brut et le convertit en ``ExercisePrompt`` ou None."""
    prompt = (raw.get("prompt") or "").strip()
    answer = (raw.get("answer") or "").strip()
    category = (raw.get("category") or "").strip() or "ai_generated"
    question_type = (raw.get("question_type") or "text").strip()
    options = raw.get("options") or []
    accepted = raw.get("accepted_answers") or []

    if not prompt or not answer:
        return None
    if category not in _ALLOWED_CATEGORIES:
        category = "ai_generated"
    if question_type not in _ALLOWED_QUESTION_TYPES:
        question_type = "text"
    if not isinstance(options, list):
        options = []
    if not isinstance(accepted, list):
        accepted = []
    options_clean = [str(o).strip() for o in options if str(o).strip()]
    accepted_clean = [str(a).strip() for a in accepted if str(a).strip()]

    # QCM : la bonne réponse doit figurer dans les options.
    if question_type == "mcq":
        if not options_clean:
            return None
        if not any(
            opt.lower() == answer.lower() for opt in options_clean
        ):
            options_clean.insert(0, answer)

    return ExercisePrompt(
        prompt=prompt,
        answer=answer,
        category=category,
        question_type=question_type,
        options=tuple(options_clean),
        accepted_answers=tuple(accepted_clean),
    )


def _persist_pool_entries(
    exercises: List[ExercisePrompt],
    *,
    student_prompt: str,
    student_id: Optional[int],
    difficulty: str,
    model_used: str,
    call_log_id: Optional[int],
) -> List[AIGeneratedExercise]:
    """Insère les exos dans ``ai_generated_exercises`` et renvoie les rows."""
    rows: List[AIGeneratedExercise] = []
    for ex in exercises:
        row = AIGeneratedExercise(
            student_prompt=student_prompt,
            prompt=ex.prompt,
            answer=ex.answer,
            category_code=ex.category,
            question_type=ex.question_type,
            options_json=json.dumps(list(ex.options)) if ex.options else None,
            accepted_answers_json=(
                json.dumps(list(ex.accepted_answers))
                if ex.accepted_answers
                else None
            ),
            difficulty=difficulty,
            model_used=model_used,
            student_id=student_id,
            call_log_id=call_log_id,
        )
        db.session.add(row)
        rows.append(row)
    db.session.flush()
    return rows


def generate_exercises(
    student_prompt: str,
    count: int,
    difficulty: str,
    student_id: Optional[int] = None,
) -> List[Tuple[ExercisePrompt, AIGeneratedExercise]]:
    """Génère ``count`` exercices via OpenAI sur le thème ``student_prompt``.

    Renvoie une liste ``(ExercisePrompt, AIGeneratedExercise_row)`` pour que
    le caller puisse créer les ``SessionExercise`` avec ``ai_exercise_id``
    correctement renseigné.

    Liste vide en cas d'erreur (clé manquante, budget dépassé, parsing KO,
    appel OpenAI en échec). Le caller doit flasher un message à l'élève.
    """
    student_prompt = (student_prompt or "").strip()
    if not student_prompt:
        return []
    if difficulty not in _ALLOWED_DIFFICULTIES:
        difficulty = "beginner"
    count = max(1, min(int(count or 1), 25))

    if is_budget_exceeded():
        logger.warning("Budget mensuel OpenAI dépassé, génération refusée.")
        return []

    client, info = get_openai_client()
    if not client:
        return []

    model = info["model"] or "gpt-4o-mini"
    api_key_source = info["source"]

    # Prompt résolu depuis la BDD (admin-éditable). Fallback sur les
    # constantes hardcodées si la ligne est absente (cas marginal : la
    # table existe mais le seed n'a pas tourné).
    prompt_row = OpenAIPrompt.get_or_create_default("generate_exercises")
    if prompt_row:
        system_prompt = prompt_row.render_system_prompt(
            difficulty=difficulty,
            categories=", ".join(_ALLOWED_CATEGORIES),
        )
        user_prompt = prompt_row.render_user_prompt(
            student_prompt=student_prompt,
            count=count,
            difficulty=difficulty,
        )
        max_output_tokens = int(
            prompt_row.get_parameters().get("max_output_tokens") or 2000
        )
    else:
        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
            difficulty=difficulty,
            categories=", ".join(_ALLOWED_CATEGORIES),
        )
        user_prompt = _USER_PROMPT_TEMPLATE.format(
            student_prompt=student_prompt,
            count=count,
            difficulty=difficulty,
        )
        max_output_tokens = 2000

    response = None
    response_text = None
    error_message = None
    response_status = "success"
    duration_ms = None
    input_tokens = None
    output_tokens = None

    started = time.monotonic()
    try:
        response = client.responses.create(
            model=model,
            input=[
                {
                    "role": "system",
                    "content": [
                        {"type": "input_text", "text": system_prompt}
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": user_prompt}
                    ],
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "exercise_batch",
                    "schema": EXERCISE_BATCH_SCHEMA,
                    "strict": True,
                },
            },
            max_output_tokens=max_output_tokens,
        )
        response_text = getattr(response, "output_text", None) or ""
        input_tokens, output_tokens = _extract_token_usage(response)
    except Exception as exc:  # noqa: BLE001
        response_status = "error"
        error_message = str(exc)
        logger.exception("Appel OpenAI en échec : %s", exc)
    finally:
        duration_ms = int((time.monotonic() - started) * 1000)

    log = ai_analytics.log_call(
        student_id=student_id,
        call_type="generate_exercises",
        model=model,
        api_key_source=api_key_source,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response_text=response_text,
        response_status=response_status,
        error_message=error_message,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_ms=duration_ms,
        context_json=json.dumps({"student_prompt": student_prompt, "count": count}),
    )
    # Flush pour obtenir l'id du log avant de référencer call_log_id.
    db.session.flush()

    if response_status != "success" or not response_text:
        db.session.commit()
        return []

    try:
        payload = json.loads(response_text)
    except (ValueError, TypeError) as exc:
        log.response_status = "error"
        log.error_message = f"JSON invalide : {exc}"
        db.session.commit()
        return []

    raw_items = payload.get("exercises") if isinstance(payload, dict) else None
    if not isinstance(raw_items, list):
        log.response_status = "error"
        log.error_message = "Champ 'exercises' absent ou invalide."
        db.session.commit()
        return []

    parsed: List[ExercisePrompt] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        ex = _coerce_exercise(raw)
        if ex:
            parsed.append(ex)

    if not parsed:
        log.response_status = "error"
        log.error_message = "Aucun exercice valide après parsing."
        db.session.commit()
        return []

    rows = _persist_pool_entries(
        parsed,
        student_prompt=student_prompt,
        student_id=student_id,
        difficulty=difficulty,
        model_used=model,
        call_log_id=log.id,
    )
    db.session.commit()

    return list(zip(parsed, rows))
