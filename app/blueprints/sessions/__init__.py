"""Blueprint ``sessions`` : déroulé d'une session de pratique
(``play_session``), sauvegarde automatique (``autosave_session``) et résumé
final (``session_summary``).

Préfixe : ``/sessions``.
"""

from datetime import datetime

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from ...extensions import db
from ...models import (
    PracticeSession,
    QuestionCategory,
    SessionTranslationLog,
    StudentBadge,
)
from ...services.answer_validation import _is_answer_correct
from ...services.auth import _current_user, _login_required
from ...services.gamification import (
    DIFFICULTY_XP,
    _award_badges,
    _select_instruction_language,
    _update_progress_from_session,
    _update_review_plan,
)


bp = Blueprint("sessions", __name__, url_prefix="/sessions")


def _display_constants():
    from ...routes import DIFFICULTY_DISPLAY, SESSION_TYPE_LABELS

    return DIFFICULTY_DISPLAY, SESSION_TYPE_LABELS


@bp.route("/<int:session_id>", methods=["GET", "POST"])
@_login_required
def play_session(session_id: int):
    session_obj = PracticeSession.query.get_or_404(session_id)
    student = session_obj.student

    if not student:
        abort(404)

    user = _current_user()
    if not (user.id == student.id or user.is_parent() or user.is_admin()):
        flash("Accès refusé.", "danger")
        return redirect(url_for("students.view_student", student_id=student.id))

    if request.method == "POST":
        correct_answers = 0
        for exercise in session_obj.exercises:
            answer_key = f"answer_{exercise.id}"
            user_answer = request.form.get(answer_key, "").strip()
            exercise.student_answer = user_answer
            exercise.is_correct = _is_answer_correct(exercise)
            if exercise.is_correct:
                correct_answers += 1
        session_obj.completed_at = datetime.utcnow()
        session_obj.correct_answers = correct_answers
        if session_obj.started_at:
            session_obj.duration_seconds = int(
                (session_obj.completed_at - session_obj.started_at).total_seconds()
            )
        _update_progress_from_session(session_obj)
        existing_badge_ids = {
            sb.badge_id
            for sb in StudentBadge.query.filter_by(student_id=session_obj.student_id).all()
        }
        _award_badges(session_obj.student_id)
        _update_review_plan(session_obj)
        db.session.commit()

        if existing_badge_ids:
            new_sbs = StudentBadge.query.filter(
                StudentBadge.student_id == session_obj.student_id,
                StudentBadge.badge_id.notin_(existing_badge_ids),
            ).all()
        else:
            new_sbs = StudentBadge.query.filter_by(student_id=session_obj.student_id).all()
        xp_gained = (session_obj.correct_answers or 0) * DIFFICULTY_XP.get(
            session_obj.difficulty or "beginner", 10
        )
        session["last_reward"] = {
            "xp_gained": xp_gained,
            "new_badge_names": [sb.badge.name for sb in new_sbs],
        }

        try:
            from ...email_service import send_session_completion_email
            send_session_completion_email(session_obj)
        except Exception:
            pass

        flash("Session terminée ! Voici ton score.", "success")
        return redirect(url_for("sessions.session_summary", session_id=session_obj.id))

    time_limit = session_obj.time_limit_seconds
    if not time_limit and session_obj.time_limit_minutes:
        time_limit = session_obj.time_limit_minutes * 60
    instruction_language = _select_instruction_language(student)
    instructions = session_obj.instructions_en if instruction_language == "en" else session_obj.instructions_fr
    if not instructions:
        instructions = (
            "Réponds aux questions sans aide et soigne l'orthographe."
            if instruction_language == "fr"
            else "Answer each question without help and check your spelling."
        )
    category_lookup = {
        cat.code: cat.name for cat in QuestionCategory.query.all()
    }
    difficulty_labels, session_type_labels = _display_constants()
    return render_template(
        "session_play.html",
        session_obj=session_obj,
        student=student,
        time_limit=time_limit,
        difficulty_labels=difficulty_labels,
        instructions=instructions,
        session_type_labels=session_type_labels,
        category_lookup=category_lookup,
    )


@bp.route("/<int:session_id>/autosave", methods=["POST"])
@_login_required
def autosave_session(session_id: int):
    session_obj = PracticeSession.query.get_or_404(session_id)
    student = session_obj.student
    if not student:
        abort(404)
    user = _current_user()
    if not (user.id == student.id or user.is_parent() or user.is_admin()):
        abort(403)
    if session_obj.completed_at:
        return {"ok": False, "error": "Session déjà terminée"}, 400
    data = request.get_json(silent=True) or {}
    for exercise in session_obj.exercises:
        key = f"answer_{exercise.id}"
        if key in data:
            raw = str(data[key]).strip()
            exercise.student_answer = raw[:255] if raw else None
    db.session.commit()
    return {"ok": True}


@bp.route("/<int:session_id>/summary")
@_login_required
def session_summary(session_id: int):
    session_obj = PracticeSession.query.get_or_404(session_id)
    student = session_obj.student
    if not student:
        abort(404)

    user = _current_user()
    if not (user.id == student.id or user.is_parent() or user.is_admin()):
        flash("Accès refusé.", "danger")
        return redirect(url_for("students.view_student", student_id=student.id))

    category_lookup = {
        category.code: category.name for category in QuestionCategory.query.all()
    }
    last_reward = session.pop("last_reward", None)
    translation_logs = (
        SessionTranslationLog.query
        .filter_by(session_id=session_id)
        .order_by(SessionTranslationLog.created_at.asc())
        .all()
    )
    difficulty_labels, session_type_labels = _display_constants()
    return render_template(
        "session_summary.html",
        session_obj=session_obj,
        category_lookup=category_lookup,
        difficulty_labels=difficulty_labels,
        session_type_labels=session_type_labels,
        last_reward=last_reward,
        translation_logs=translation_logs,
    )
