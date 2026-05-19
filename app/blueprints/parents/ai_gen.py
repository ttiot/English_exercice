"""Route ``/parents/students/<id>/generate-ai-exercises`` : générer un set préparé via OpenAI pour un élève donné."""

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


@bp.route(
    "/students/<int:student_id>/generate-ai-exercises",
    methods=["GET", "POST"],
)
@_parent_required
def parent_generate_ai_exercises(student_id: int):
    student = _get_student_or_404(student_id)
    _assert_student_access(_current_user(), student)

    if request.method == "POST":
        from ...services.session_builder import (
            AIGenerationError,
            generate_ai_exercises_for_student,
            persist_ai_as_prepared_set,
        )

        difficulty = request.form.get("difficulty", "beginner").strip()
        if difficulty not in DIFFICULTY_LEVELS:
            difficulty = "beginner"
        try:
            question_count = int(request.form.get("question_count", 10))
            question_count = max(5, min(25, question_count))
        except (ValueError, TypeError):
            question_count = 10

        student_prompt_raw = sanitize_text_input(request.form.get("student_prompt", ""))

        try:
            prompt, ai_pairs = generate_ai_exercises_for_student(
                student_prompt=student_prompt_raw,
                difficulty=difficulty,
                question_count=question_count,
                student=student,
            )
        except AIGenerationError as exc:
            flash(exc.message, exc.severity)
            return render_template(
                "parent_ai_generate.html",
                student=student,
                difficulty_labels=_display_constants()[1],
                form_data={
                    "student_prompt": student_prompt_raw,
                    "difficulty": difficulty,
                    "question_count": question_count,
                },
            )

        persist_ai_as_prepared_set(student=student, prompt=prompt, ai_pairs=ai_pairs)
        flash(
            f"{len(ai_pairs)} exercice(s) générés et assignés à {student.full_name()}. "
            "Ils seront proposés lors de sa prochaine session.",
            "success",
        )
        return redirect(url_for("students.view_student", student_id=student_id))

    return render_template(
        "parent_ai_generate.html",
        student=student,
        difficulty_labels=_display_constants()[1],
        form_data=None,
    )
