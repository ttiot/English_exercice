"""Routes ``/parents/sessions/<id>/*`` : suppression d'une session ou corrections post-jeu (toggle correct, édition d'une question)."""

from collections import defaultdict
from datetime import date, datetime
from io import StringIO
from typing import Dict, List, Optional, Tuple

import csv
import json
import re

from flask import (
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from ...exercise_factory import (
    DIFFICULTY_LEVELS,
    normalize_difficulty,
)
from ...extensions import db
from ...models import (
    ExerciseItem,
    PracticeSession,
    PreparedExerciseQuestion,
    PreparedExerciseSet,
    QuestionCategory,
    SessionExercise,
    Student,
    StudentBadge,
    StudentSkillProgress,
    WeeklyGoal,
)
from ...services.analytics import (
    _build_simple_pdf,
    _quarter_range,
    _student_recurring_errors,
    _student_theme_summary,
)
from ...services.auth import (
    _assert_student_access,
    _current_user,
    _get_student_or_404,
    _get_visible_students,
    _parent_required,
    is_safe_url,
)
from ...services.curriculum import (
    DOMAIN_CHOICES,
    _filter_categories,
)
from ...services.gamification import (
    _compute_weekly_progress,
    _current_week_range,
    _get_weekly_goal,
)
from ...validators import (
    sanitize_text_input,
    validate_question_content,
)
from . import (
    _csv_safe,
    _display_constants,
    _parse_import_rows_lazy,
    _preserve_filters,
    _slugify_label,
    bp,
)


@bp.route("/sessions/<int:session_id>/delete", methods=["POST"])
@_parent_required
def delete_session(session_id: int):
    session_obj = PracticeSession.query.get(session_id)
    if not session_obj:
        flash("Session introuvable ou déjà supprimée.", "warning")
        return redirect(url_for("parents.parent_dashboard"))

    _assert_student_access(_current_user(), session_obj.student)
    student_id = session_obj.student_id

    db.session.delete(session_obj)
    db.session.commit()

    flash("La session a été supprimée.", "success")
    return redirect(url_for("students.view_student", student_id=student_id))


@bp.route("/sessions/<int:session_id>/exercises/<int:exercise_id>/toggle-correct",
    methods=["POST"],
)


@_parent_required
def toggle_exercise_correct(session_id: int, exercise_id: int):
    session_obj = PracticeSession.query.get_or_404(session_id)
    exercise = SessionExercise.query.get_or_404(exercise_id)
    if exercise.session_id != session_id:
        abort(404)
    _assert_student_access(_current_user(), session_obj.student)

    was_correct = exercise.is_correct
    exercise.is_correct = not was_correct

    session_obj.correct_answers = sum(1 for ex in session_obj.exercises if ex.is_correct)

    category = QuestionCategory.query.filter_by(code=exercise.category).first()
    if category:
        progress = StudentSkillProgress.query.filter_by(
            student_id=session_obj.student_id,
            category_id=category.id,
        ).first()
        if progress:
            delta = 1 if not was_correct else -1
            progress.correct_attempts = max(0, (progress.correct_attempts or 0) + delta)
            progress.mastery = (
                (progress.correct_attempts / progress.total_attempts) * 100
                if progress.total_attempts
                else 0.0
            )

    db.session.commit()
    action = "correcte" if exercise.is_correct else "incorrecte"
    flash(f"Réponse marquée comme {action}.", "success")
    return redirect(url_for("sessions.session_summary", session_id=session_id))


@bp.route("/sessions/<int:session_id>/exercises/<int:exercise_id>/edit",
    methods=["GET", "POST"],
)


@_parent_required
def edit_exercise(session_id: int, exercise_id: int):
    session_obj = PracticeSession.query.get_or_404(session_id)
    exercise = SessionExercise.query.get_or_404(exercise_id)
    if exercise.session_id != session_id:
        abort(404)
    _assert_student_access(_current_user(), session_obj.student)

    categories = QuestionCategory.query.order_by(QuestionCategory.order_index).all()

    if request.method == "POST":
        prompt = sanitize_text_input(request.form.get("prompt", ""))
        correct_answer = sanitize_text_input(request.form.get("correct_answer", ""))
        category_code = request.form.get("category", exercise.category).strip()

        valid, msg = validate_question_content(prompt, correct_answer)
        if not valid:
            flash(msg, "danger")
            return render_template(
                "edit_exercise.html",
                session_obj=session_obj,
                exercise=exercise,
                categories=categories,
                form_data={"prompt": prompt, "correct_answer": correct_answer, "category": category_code},
            )

        known_codes = {c.code for c in categories}
        if category_code not in known_codes:
            category_code = exercise.category

        exercise.prompt = prompt
        exercise.correct_answer = correct_answer
        exercise.category = category_code
        db.session.commit()

        flash("Exercice modifié avec succès.", "success")
        return redirect(url_for("sessions.session_summary", session_id=session_id))

    return render_template(
        "edit_exercise.html",
        session_obj=session_obj,
        exercise=exercise,
        categories=categories,
        form_data=None,
    )
