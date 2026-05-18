"""Blueprint ``api`` : endpoints JSON utilisés par les pages élèves (traduction
à la volée pendant la session, etc.).

Préfixe d'URL : ``/api``.
"""

from flask import Blueprint, request

from ...services.auth import _current_user, _login_required
from ...validators import sanitize_text_input


bp = Blueprint("api", __name__, url_prefix="/api")


@bp.route("/translate-word", methods=["POST"])
@_login_required
def translate_word_api():
    from ...services.translator import MAX_WORD_LENGTH, translate_word

    data = request.get_json(silent=True) or {}
    word = sanitize_text_input(str(data.get("word", "")).strip())
    context = sanitize_text_input(str(data.get("context", "")).strip())

    if not word:
        return {"error": "Mot manquant."}, 400
    if len(word) > MAX_WORD_LENGTH:
        return {"error": "Sélection trop longue (200 caractères max)."}, 400

    raw_session_id = data.get("session_id")
    try:
        linked_session_id = int(raw_session_id) if raw_session_id is not None else None
    except (TypeError, ValueError):
        linked_session_id = None

    user = _current_user()
    student_id = user.id if user else None

    result = translate_word(word, context, session_id=linked_session_id, student_id=student_id)
    if result is None:
        return {"error": "Traduction impossible. L'IA n'est pas disponible."}, 503

    return result
