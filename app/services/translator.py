"""Service de traduction de mots/expressions via l'API OpenAI.

Pipeline :
1. Normalise le mot (minuscules + strip).
2. Cherche en cache dans ``WordTranslation`` (cache global, toutes sessions confondues).
3. Si absent : appelle l'IA avec un JSON schema strict, persiste le résultat.
4. Dans tous les cas, logue dans ``SessionTranslationLog`` si un ``session_id`` est fourni.
5. Retourne ``{"translation": str, "examples": list[str], "cached": bool}``.

Les appels IA sont également audités dans ``AICallLog`` via le mécanisme existant.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

from .. import db
from ..models import AICallLog, SessionTranslationLog, WordTranslation
from . import ai_analytics
from .ai_generator import _SYSTEM_PROMPT_TRANSLATION, get_openai_client

logger = logging.getLogger(__name__)

MAX_WORD_LENGTH = 200

_TRANSLATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["translation", "examples"],
    "properties": {
        "translation": {
            "type": "string",
            "description": "Traduction du mot ou de l'expression dans l'autre langue.",
        },
        "examples": {
            "type": "array",
            "description": "2 exemples d'utilisation simples, niveau collège, avec traduction entre parenthèses.",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 3,
        },
    },
}


def _get_system_prompt() -> tuple[str, int]:
    """Renvoie (system_prompt, max_output_tokens) depuis la BDD ou le fallback."""
    try:
        from ..models import OpenAIPrompt
        prompt_obj = OpenAIPrompt.get_or_create_default("word_translation")
        if prompt_obj:
            params = prompt_obj.get_parameters()
            return prompt_obj.system_prompt, params.get("max_output_tokens", 300)
    except Exception:  # noqa: BLE001
        pass
    return _SYSTEM_PROMPT_TRANSLATION, 300


def _log_session_translation(
    session_id: int,
    student_id: Optional[int],
    word: str,
    translation: str,
    was_cached: bool,
    ai_call_log_id: Optional[int],
) -> None:
    """Crée une entrée SessionTranslationLog et committe."""
    try:
        entry = SessionTranslationLog(
            session_id=session_id,
            student_id=student_id,
            word=word,
            translation=translation,
            was_cached=was_cached,
            ai_call_log_id=ai_call_log_id,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Impossible de loguer SessionTranslationLog : %s", exc)
        db.session.rollback()


def translate_word(
    word: str,
    context: str = "",
    session_id: Optional[int] = None,
    student_id: Optional[int] = None,
) -> Optional[dict]:
    """Traduit ``word`` (avec ``context`` optionnel) et met en cache le résultat.

    Si ``session_id`` est fourni, enregistre un ``SessionTranslationLog``
    (même pour les hits de cache).

    Retourne ``None`` si l'IA n'est pas configurée ou en cas d'erreur.
    """
    normalized = word.strip().lower()
    if not normalized or len(normalized) > MAX_WORD_LENGTH:
        return None

    cached = WordTranslation.query.filter_by(word=normalized).first()
    if cached:
        if session_id:
            _log_session_translation(
                session_id=session_id,
                student_id=student_id,
                word=normalized,
                translation=cached.translation,
                was_cached=True,
                ai_call_log_id=None,
            )
        return {
            "translation": cached.translation,
            "examples": cached.examples,
            "cached": True,
        }

    client, info = get_openai_client()
    if not client:
        return None

    system_prompt, max_tokens = _get_system_prompt()

    user_prompt = f'Traduis : "{word}"'
    if context:
        ctx_snippet = context.strip()[:300]
        user_prompt += f'\nContexte : « {ctx_snippet} »'

    start = time.monotonic()
    try:
        response = client.responses.create(
            model=info["model"],
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "translation",
                    "schema": _TRANSLATION_SCHEMA,
                    "strict": True,
                }
            },
            max_output_tokens=max_tokens,
        )
        duration_ms = int((time.monotonic() - start) * 1000)

        raw = response.output_text
        data = json.loads(raw)
        translation = data.get("translation", "").strip()
        examples = data.get("examples", [])

        if not translation:
            return None

        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "output_tokens", 0) if usage else 0

        ai_analytics.log_call(
            student_id,
            call_type="word_translation",
            model=info["model"],
            api_key_source=info["source"],
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_text=raw,
            response_status="success",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
        )

        entry = WordTranslation(
            word=normalized,
            translation=translation,
            examples_json=json.dumps(examples, ensure_ascii=False),
        )
        db.session.add(entry)
        db.session.commit()

        # Récupérer l'id du log IA créé (dernier log de ce type pour cet étudiant)
        ai_log_id: Optional[int] = None
        try:
            last_log = (
                AICallLog.query
                .filter_by(call_type="word_translation", student_id=student_id)
                .order_by(AICallLog.id.desc())
                .first()
            )
            if last_log:
                ai_log_id = last_log.id
        except Exception:  # noqa: BLE001
            pass

        if session_id:
            _log_session_translation(
                session_id=session_id,
                student_id=student_id,
                word=normalized,
                translation=translation,
                was_cached=False,
                ai_call_log_id=ai_log_id,
            )

        return {"translation": translation, "examples": examples, "cached": False}

    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning("Erreur traduction IA pour %r : %s", word, exc)
        ai_analytics.log_call(
            student_id,
            call_type="word_translation",
            model=info["model"],
            api_key_source=info["source"],
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_text="",
            response_status="error",
            error_message=str(exc),
            duration_ms=duration_ms,
        )
        return None
