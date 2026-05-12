"""Service de traduction de mots/expressions via l'API OpenAI.

Pipeline :
1. Normalise le mot (minuscules + strip).
2. Cherche en cache dans ``WordTranslation`` (cache global, toutes sessions confondues).
3. Si absent : appelle l'IA avec un JSON schema strict, persiste le résultat.
4. Retourne ``{"translation": str, "examples": list[str], "cached": bool}``.

Tous les appels IA sont audités dans ``AICallLog`` via le mécanisme existant.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

from .. import db
from ..models import AICallLog, WordTranslation
from .ai_generator import get_openai_client

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

_SYSTEM_PROMPT = (
    "Tu es un assistant pédagogique pour des collégiens français (6ème/5ème) "
    "qui apprennent l'anglais. Quand on te donne un mot ou une expression, "
    "détecte sa langue, traduis-le dans l'autre langue (anglais ↔ français) "
    "et donne 2 exemples d'utilisation simples adaptés au niveau collège, "
    "chacun suivi de sa traduction entre parenthèses. "
    "Réponds uniquement avec le JSON demandé, sans commentaire."
)


def translate_word(word: str, context: str = "") -> Optional[dict]:
    """Traduit ``word`` (avec ``context`` optionnel) et met en cache le résultat.

    Retourne ``None`` si l'IA n'est pas configurée ou en cas d'erreur.
    """
    normalized = word.strip().lower()
    if not normalized or len(normalized) > MAX_WORD_LENGTH:
        return None

    cached = WordTranslation.query.filter_by(word=normalized).first()
    if cached:
        return {
            "translation": cached.translation,
            "examples": cached.examples,
            "cached": True,
        }

    client, info = get_openai_client()
    if not client:
        return None

    user_prompt = f'Traduis : "{word}"'
    if context:
        ctx_snippet = context.strip()[:300]
        user_prompt += f'\nContexte : « {ctx_snippet} »'

    start = time.monotonic()
    try:
        response = client.responses.create(
            model=info["model"],
            input=[
                {"role": "system", "content": _SYSTEM_PROMPT},
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
            max_output_tokens=300,
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

        AICallLog.log_call(
            None,
            call_type="word_translation",
            model=info["model"],
            api_key_source=info["source"],
            system_prompt=_SYSTEM_PROMPT,
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

        return {"translation": translation, "examples": examples, "cached": False}

    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning("Erreur traduction IA pour %r : %s", word, exc)
        AICallLog.log_call(
            None,
            call_type="word_translation",
            model=info["model"],
            api_key_source=info["source"],
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_text="",
            response_status="error",
            error_message=str(exc),
            duration_ms=duration_ms,
        )
        return None
