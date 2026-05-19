"""Routes ``/parents/dashboard``, ``/weekly-goal``, ``/report`` : vue d'ensemble + objectifs hebdo + export rapport trimestriel."""

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


@bp.route("/dashboard")
@_parent_required
def parent_dashboard():
    user = _current_user()
    students = _get_visible_students(user)
    prepared_sets = (
        PreparedExerciseSet.query.filter_by(is_used=False)
        .order_by(PreparedExerciseSet.created_at.desc())
        .all()
    )
    categories = QuestionCategory.query.order_by(QuestionCategory.name).all()

    stats = []
    week_start, week_end = _current_week_range()
    for student in students:
        sessions = PracticeSession.query.filter_by(student_id=student.id).all()
        total_sessions = len(sessions)
        total_questions = sum(session.total_questions or 0 for session in sessions)
        total_correct = sum(session.correct_answers or 0 for session in sessions)
        average_score = (total_correct / total_questions * 100) if total_questions else 0
        total_seconds = sum(session.duration_seconds or 0 for session in sessions)
        weekly_goal = _get_weekly_goal(student.id, week_start)
        weekly_progress = _compute_weekly_progress(student, week_start)
        theme_summary = _student_theme_summary(student.id)
        recurring_errors = _student_recurring_errors(student.id)
        earned_badges = StudentBadge.query.filter_by(student_id=student.id).count()
        stats.append(
            {
                "student": student,
                "total_sessions": total_sessions,
                "average_score": round(average_score, 1) if average_score else 0,
                "total_minutes": round(total_seconds / 60, 1) if total_seconds else 0.0,
                "weekly_goal": weekly_goal,
                "weekly_progress": weekly_progress,
                "week_start": week_start,
                "week_end": week_end,
                "theme_summary": theme_summary,
                "recurring_errors": recurring_errors,
                "earned_badges": earned_badges,
            }
        )

    return render_template(
        "parent_dashboard.html",
        stats=stats,
        prepared_sets=prepared_sets,
        students=students,
        categories=categories,
        week_start=week_start,
        week_end=week_end,
    )


@bp.route("/students/<int:student_id>/weekly-goal", methods=["POST"])
@_parent_required
def update_weekly_goal(student_id: int):
    student = _get_student_or_404(student_id)
    _assert_student_access(_current_user(), student)
    week_start = _current_week_range()[0]

    try:
        target_sessions = int(request.form.get("target_sessions", 3))
        target_minutes = int(request.form.get("target_minutes", 45))
        target_accuracy = float(request.form.get("target_accuracy", 70))
        target_challenges = int(request.form.get("target_challenges", 1))
    except ValueError:
        flash("Les objectifs doivent être des nombres valides.", "danger")
        return redirect(url_for("parents.parent_dashboard"))

    goal = _get_weekly_goal(student.id, week_start)
    if not goal:
        goal = WeeklyGoal(student_id=student.id, week_start=week_start)
        db.session.add(goal)

    goal.target_sessions = max(1, target_sessions)
    goal.target_minutes = max(5, target_minutes)
    goal.target_accuracy = max(0.0, min(100.0, target_accuracy))
    goal.target_challenges = max(0, target_challenges)
    db.session.commit()

    flash("Objectifs hebdomadaires mis à jour.", "success")
    return redirect(url_for("parents.parent_dashboard"))


@bp.route("/students/<int:student_id>/report")
@_parent_required
def export_quarter_report(student_id: int):
    student = _get_student_or_404(student_id)
    _assert_student_access(_current_user(), student)
    today = date.today()
    quarter = request.args.get("quarter")
    year = request.args.get("year")
    try:
        quarter_value = int(quarter) if quarter else ((today.month - 1) // 3 + 1)
        year_value = int(year) if year else today.year
    except ValueError:
        quarter_value = (today.month - 1) // 3 + 1
        year_value = today.year

    start_date, end_date = _quarter_range(year_value, quarter_value)
    sessions = (
        PracticeSession.query.filter(
            PracticeSession.student_id == student.id,
            PracticeSession.started_at >= datetime.combine(start_date, datetime.min.time()),
            PracticeSession.started_at <= datetime.combine(end_date, datetime.max.time()),
        )
        .order_by(PracticeSession.started_at.asc())
        .all()
    )

    total_questions = sum(session.total_questions or 0 for session in sessions)
    total_correct = sum(session.correct_answers or 0 for session in sessions)
    total_seconds = sum(session.duration_seconds or 0 for session in sessions)
    average_score = (total_correct / total_questions * 100) if total_questions else 0.0

    session_ids = [session.id for session in sessions]
    exercises = []
    if session_ids:
        exercises = SessionExercise.query.filter(SessionExercise.session_id.in_(session_ids)).all()

    category_lookup = {category.code: category for category in QuestionCategory.query.all()}
    domain_labels = {code: label for code, label in DOMAIN_CHOICES}
    theme_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0})
    error_counts: Dict[str, Dict[str, object]] = {}
    for exercise in exercises:
        category = category_lookup.get(exercise.category)
        domain = category.domain if category and category.domain else "autre"
        theme_stats[domain]["total"] += 1
        if exercise.is_correct:
            theme_stats[domain]["correct"] += 1
        if not exercise.is_correct:
            key = f"{exercise.category}:{exercise.prompt}"
            entry = error_counts.setdefault(
                key, {"prompt": exercise.prompt, "category": exercise.category, "count": 0}
            )
            entry["count"] += 1

    theme_summary = []
    for domain, values in theme_stats.items():
        total = values["total"]
        correct = values["correct"]
        rate = (correct / total * 100) if total else 0
        theme_summary.append(
            {
                "domain": domain_labels.get(domain, domain),
                "total": total,
                "correct": correct,
                "rate": round(rate, 1) if rate else 0,
            }
        )
    theme_summary = sorted(theme_summary, key=lambda item: item["domain"])
    recurring_errors = sorted(
        error_counts.values(), key=lambda item: item["count"], reverse=True
    )[:10]

    report_format = request.args.get("format", "csv").lower()
    if report_format == "pdf":
        lines = [
            f"Bilan trimestriel - {student.full_name()}",
            f"Période: {start_date.strftime('%d/%m/%Y')} au {end_date.strftime('%d/%m/%Y')}",
            f"Sessions: {len(sessions)}",
            f"Score moyen: {average_score:.1f}%",
            f"Temps total: {round(total_seconds / 60, 1)} min",
            "",
            "Evolution par theme:",
        ]
        for item in theme_summary:
            lines.append(
                f"- {item['domain']}: {item['rate']}% ({item['correct']}/{item['total']})"
            )
        if recurring_errors:
            lines.append("")
            lines.append("Erreurs recurrentes:")
            for error in recurring_errors:
                lines.append(f"- {error['prompt']} ({error['count']}x)")
        pdf_bytes = _build_simple_pdf(lines)
        safe_fname = re.sub(r"[^a-zA-Z0-9_\-]", "_", student.first_name)
        filename = f"bilan_{safe_fname}_{year_value}_T{quarter_value}.pdf"
        return current_app.response_class(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            },
        )

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Bilan trimestriel", _csv_safe(student.full_name())])
    writer.writerow(["Periode", start_date.isoformat(), end_date.isoformat()])
    writer.writerow([])
    writer.writerow(["Sessions", len(sessions)])
    writer.writerow(["Score moyen (%)", f"{average_score:.1f}"])
    writer.writerow(["Temps total (minutes)", f"{round(total_seconds / 60, 1)}"])
    writer.writerow([])
    writer.writerow(["Evolution par theme"])
    writer.writerow(["Theme", "Questions", "Bonnes reponses", "Taux (%)"])
    for item in theme_summary:
        writer.writerow([_csv_safe(item["domain"]), item["total"], item["correct"], item["rate"]])
    if recurring_errors:
        writer.writerow([])
        writer.writerow(["Erreurs recurrentes"])
        writer.writerow(["Question", "Occurrences", "Categorie"])
        for error in recurring_errors:
            writer.writerow([_csv_safe(error["prompt"]), error["count"], _csv_safe(error["category"])])

    safe_fname = re.sub(r"[^a-zA-Z0-9_\-]", "_", student.first_name)
    filename = f"bilan_{safe_fname}_{year_value}_T{quarter_value}.csv"
    return current_app.response_class(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        },
    )
