"""Routes ``/parents/categories/*`` : CRUD des catégories de questions."""

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


@bp.route("/categories/new", methods=["POST"])
@_parent_required
def create_category():

    label = request.form.get("name", "").strip()
    if not label:
        flash("Le nom de la catégorie est requis.", "danger")
        return redirect(url_for("parents.parent_dashboard"))

    code = _slugify_label(label)
    existing = QuestionCategory.query.filter(
        (QuestionCategory.code == code) | (QuestionCategory.name == label)
    ).first()
    if existing:
        flash("Cette catégorie existe déjà.", "warning")
        return redirect(url_for("parents.parent_dashboard"))

    db.session.add(QuestionCategory(code=code, name=label))
    db.session.commit()
    flash("Catégorie créée.", "success")
    return redirect(url_for("parents.parent_dashboard"))


@bp.route("/categories/<int:category_id>/rename", methods=["POST"])
@_parent_required
def rename_category(category_id: int):

    category = QuestionCategory.query.get_or_404(category_id)
    new_label = request.form.get("name", "").strip()
    if not new_label:
        flash("Le nom ne peut pas être vide.", "danger")
        return redirect(url_for("parents.parent_dashboard"))

    new_code = _slugify_label(new_label)
    conflict = QuestionCategory.query.filter(
        (QuestionCategory.id != category.id)
        & ((QuestionCategory.code == new_code) | (QuestionCategory.name == new_label))
    ).first()
    if conflict:
        flash("Une autre catégorie porte déjà ce nom.", "warning")
        return redirect(url_for("parents.parent_dashboard"))

    old_code = category.code
    category.name = new_label
    category.code = new_code

    SessionExercise.query.filter_by(category=old_code).update({"category": new_code})
    PreparedExerciseQuestion.query.filter_by(category_code=old_code).update(
        {"category_code": new_code}
    )

    db.session.commit()
    flash("Catégorie mise à jour.", "success")
    return redirect(url_for("parents.parent_dashboard"))


@bp.route("/categories/<int:category_id>/delete", methods=["POST"])
@_parent_required
def delete_category(category_id: int):

    category = QuestionCategory.query.get_or_404(category_id)

    in_use = SessionExercise.query.filter_by(category=category.code).first() or PreparedExerciseQuestion.query.filter_by(
        category_code=category.code
    ).first()
    if in_use:
        flash("Impossible de supprimer une catégorie utilisée.", "warning")
        return redirect(url_for("parents.parent_dashboard"))

    db.session.delete(category)
    db.session.commit()
    flash("Catégorie supprimée.", "success")
    return redirect(url_for("parents.parent_dashboard"))
