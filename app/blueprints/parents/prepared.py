"""Routes ``/parents/prepared-exercises/new`` et ``/parents/import`` : création manuelle et import bulk d'exercices préparés."""

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


@bp.route("/prepared-exercises/new", methods=["GET", "POST"])
@_parent_required
def create_prepared_exercise():
    user = _current_user()
    students = _get_visible_students(user)
    categories = QuestionCategory.query.order_by(QuestionCategory.name).all()

    if request.method == "POST":
        title = request.form.get("title", "").strip() or "Exercice préparé"
        student_id = request.form.get("student_id")
        use_time_limit = request.form.get("use_time_limit") == "on"
        minutes_raw = request.form.get("limit_minutes", "0").strip()
        seconds_raw = request.form.get("limit_seconds", "0").strip()
        instructions_fr = sanitize_text_input(request.form.get("instructions_fr", "")) or None
        instructions_en = sanitize_text_input(request.form.get("instructions_en", "")) or None

        try:
            minutes_value = int(minutes_raw or 0)
            seconds_value = int(seconds_raw or 0)
        except ValueError:
            flash("Le temps doit être indiqué en nombres entiers.", "danger")
            return redirect(url_for("parents.create_prepared_exercise"))

        total_seconds = minutes_value * 60 + seconds_value
        if use_time_limit and total_seconds <= 0:
            flash("Indiquez un temps supérieur à zéro.", "danger")
            return redirect(url_for("parents.create_prepared_exercise"))

        prompts = request.form.getlist("question_prompt[]")
        answers = request.form.getlist("question_answer[]")
        categories_selected = request.form.getlist("question_category[]")

        questions_payload = []
        for prompt_text, answer_text, category_code in zip(
            prompts, answers, categories_selected
        ):
            prompt_clean = sanitize_text_input(prompt_text)
            answer_clean = sanitize_text_input(answer_text)
            category_code = (category_code or "custom").strip() or "custom"
            
            # Validation stricte du contenu des questions
            if prompt_clean and answer_clean:
                content_valid, content_message = validate_question_content(prompt_clean, answer_clean)
                if not content_valid:
                    flash(f"Question invalide : {content_message}", "danger")
                    return redirect(url_for("parents.create_prepared_exercise"))
                
                questions_payload.append(
                    (prompt_clean, answer_clean, category_code)
                )

        if not questions_payload:
            flash("Ajoutez au moins une question valide.", "danger")
            return redirect(url_for("parents.create_prepared_exercise"))

        student_obj: Optional[Student] = None
        if student_id and student_id != "all":
            try:
                student_obj = Student.query.get(int(student_id))
            except (TypeError, ValueError):
                student_obj = None
            if student_obj and student_obj.role != "student":
                student_obj = None

        from ...services.imports import persist_prepared_set

        rows = [
            {"prompt": prompt_clean, "answer": answer_clean, "category": category_code}
            for prompt_clean, answer_clean, category_code in questions_payload
        ]
        persist_prepared_set(
            title=title,
            student=student_obj,
            rows=rows,
            instructions_fr=instructions_fr,
            instructions_en=instructions_en,
            use_time_limit=use_time_limit,
            time_limit_seconds=total_seconds,
        )

        flash("Exercice préparé enregistré.", "success")
        return redirect(url_for("parents.parent_dashboard"))

    return render_template(
        "prepared_exercise_form.html",
        students=students,
        categories=categories,
    )


@bp.route("/import", methods=["GET", "POST"])
@_parent_required
def import_exercises():
    user = _current_user()
    students = _get_visible_students(user)
    categories = QuestionCategory.query.order_by(QuestionCategory.name).all()
    category_codes = {category.code for category in categories}

    if request.method == "POST":
        title = request.form.get("title", "").strip() or "Import de questions"
        student_id = request.form.get("student_id")
        import_format = request.form.get("format", "csv")
        if import_format not in {"anki", "csv"}:
            import_format = "csv"
        delimiter = request.form.get("delimiter", ",").strip() or ","
        instructions_fr = sanitize_text_input(request.form.get("instructions_fr", "")) or None
        instructions_en = sanitize_text_input(request.form.get("instructions_en", "")) or None
        file = request.files.get("file")

        if not file or not file.filename:
            flash("Ajoutez un fichier à importer.", "danger")
            return redirect(url_for("parents.import_exercises"))

        content = file.read().decode("utf-8", errors="ignore")
        rows = _parse_import_rows_lazy(content, import_format, delimiter)
        if not rows:
            flash("Aucune question valide trouvée dans le fichier.", "warning")
            return redirect(url_for("parents.import_exercises"))

        student_obj: Optional[Student] = None
        if student_id and student_id != "all":
            try:
                student_obj = Student.query.get(int(student_id))
            except (TypeError, ValueError):
                student_obj = None
            if student_obj and student_obj.role != "student":
                student_obj = None

        from ...services.imports import persist_prepared_set

        _exercise_set, warnings = persist_prepared_set(
            title=title,
            student=student_obj,
            rows=rows,
            instructions_fr=instructions_fr,
            instructions_en=instructions_en,
            valid_category_codes=category_codes,
            validate_each_row=True,
        )
        for warning in warnings:
            flash(warning, "warning")
        flash("Import terminé : questions ajoutées.", "success")
        return redirect(url_for("parents.parent_dashboard"))

    return render_template(
        "import_exercises.html",
        students=students,
        categories=categories,
    )
