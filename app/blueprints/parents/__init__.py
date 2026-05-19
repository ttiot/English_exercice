"""Blueprint ``parents`` : dashboard, gestion des catégories, sessions,
exercices et générations IA réservés aux parents/admins.

C'est le blueprint le plus volumineux (19 routes) car il regroupe toute la
zone d'administration parentale ; les routes sont laissées dans un seul
fichier pour préserver la cohérence avec les imports/helpers partagés.

Préfixe : ``/parents``.
"""

from collections import defaultdict
from datetime import date, datetime
from io import StringIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

import csv
import json
import re

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.utils import secure_filename

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


bp = Blueprint("parents", __name__, url_prefix="/parents")


def _slugify_label(label):
    from ...routes import _slugify_label as impl

    return impl(label)


def _csv_safe(value):
    from ...routes import _csv_safe as impl

    return impl(value)


def _display_constants():
    from ...routes import DIFFICULTY_CHOICES, DIFFICULTY_DISPLAY

    return DIFFICULTY_CHOICES, DIFFICULTY_DISPLAY


def _parse_import_rows_lazy(content, fmt, delim):
    from ...services.imports import _parse_import_rows

    return _parse_import_rows(content, fmt, delim)


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


@bp.route("/students/<int:student_id>/generate-ai-exercises",
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


# ─── Unified Exercise Manager ─────────────────────────────────────────────────


def _preserve_filters(source) -> dict:
    keys = ("type", "q", "domain", "difficulty", "student_id", "date_from", "date_to")
    return {k: source.get(k) for k in keys if source.get(k)}


@bp.route("/exercises")
@_parent_required
def list_all_exercises():
    PER_PAGE = 30
    try:
        page = max(int(request.args.get("page", 1) or 1), 1)
    except (TypeError, ValueError):
        page = 1

    ex_type = request.args.get("type", "").strip()
    q = request.args.get("q", "").strip()
    domain = request.args.get("domain", "").strip()
    difficulty = request.args.get("difficulty", "").strip()
    student_id_raw = request.args.get("student_id", "").strip()
    date_from_raw = request.args.get("date_from", "").strip()
    date_to_raw = request.args.get("date_to", "").strip()

    domain_category_codes: set = set()
    if domain:
        domain_category_codes = {c.code for c in _filter_categories(domain, "", "", "")}

    results = []

    if not ex_type or ex_type == "session":
        sq = SessionExercise.query.join(PracticeSession)
        if q:
            sq = sq.filter(SessionExercise.prompt.ilike(f"%{q}%"))
        if domain and domain_category_codes:
            sq = sq.filter(SessionExercise.category.in_(domain_category_codes))
        if difficulty:
            sq = sq.filter(PracticeSession.difficulty == difficulty)
        if student_id_raw:
            try:
                sq = sq.filter(PracticeSession.student_id == int(student_id_raw))
            except (TypeError, ValueError):
                pass
        if date_from_raw:
            try:
                sq = sq.filter(
                    PracticeSession.started_at >= datetime.fromisoformat(date_from_raw)
                )
            except ValueError:
                pass
        if date_to_raw:
            try:
                sq = sq.filter(
                    PracticeSession.started_at <= datetime.fromisoformat(date_to_raw)
                )
            except ValueError:
                pass
        for ex in sq.all():
            sess = ex.session
            results.append({
                "type": "session",
                "id": ex.id,
                "prompt": ex.prompt,
                "answer": ex.correct_answer,
                "category_code": ex.category,
                "difficulty": sess.difficulty if sess else None,
                "student_id": sess.student_id if sess else None,
                "date": sess.started_at if sess else None,
                "edit_url": url_for("parents.edit_exercise",
                    session_id=ex.session_id,
                    exercise_id=ex.id,
                ),
                "is_active": None,
            })

    if not ex_type or ex_type == "prepared":
        pq = PreparedExerciseQuestion.query
        if q:
            pq = pq.filter(PreparedExerciseQuestion.prompt.ilike(f"%{q}%"))
        if domain and domain_category_codes:
            pq = pq.filter(
                PreparedExerciseQuestion.category_code.in_(domain_category_codes)
            )
        if student_id_raw:
            try:
                sid = int(student_id_raw)
                pq = pq.join(PreparedExerciseSet).filter(
                    db.or_(
                        PreparedExerciseSet.student_id == sid,
                        PreparedExerciseSet.student_id.is_(None),
                    )
                )
            except (TypeError, ValueError):
                pass
        for ex in pq.all():
            es = ex.exercise_set
            results.append({
                "type": "prepared",
                "id": ex.id,
                "prompt": ex.prompt,
                "answer": ex.answer,
                "category_code": ex.category_code,
                "difficulty": None,
                "student_id": es.student_id if es else None,
                "date": es.created_at if es else ex.created_at,
                "edit_url": url_for("parents.edit_prepared_question", question_id=ex.id),
                "is_active": None,
            })

    if not ex_type or ex_type == "bank":
        bq = ExerciseItem.query
        if q:
            bq = bq.filter(ExerciseItem.prompt.ilike(f"%{q}%"))
        if domain:
            bq = bq.join(ExerciseItem.category).filter(
                QuestionCategory.domain == domain
            )
        if difficulty:
            bq = bq.filter(ExerciseItem.difficulty == difficulty)
        for ex in bq.all():
            results.append({
                "type": "bank",
                "id": ex.id,
                "prompt": ex.prompt,
                "answer": ex.answer,
                "category_code": ex.category.code if ex.category else None,
                "difficulty": ex.difficulty,
                "student_id": None,
                "date": ex.created_at,
                "edit_url": url_for("parents.edit_exercise_item", item_id=ex.id),
                "is_active": ex.is_active,
            })

    results.sort(key=lambda r: r["date"] or datetime.min, reverse=True)

    total = len(results)
    page_items = results[(page - 1) * PER_PAGE: page * PER_PAGE]

    all_codes = {r["category_code"] for r in page_items if r["category_code"]}
    cat_map: dict = {}
    if all_codes:
        cat_map = {
            c.code: c.name
            for c in QuestionCategory.query.filter(
                QuestionCategory.code.in_(all_codes)
            ).all()
        }
    for r in page_items:
        r["category_name"] = cat_map.get(r["category_code"] or "", r["category_code"] or "—")

    students = _get_visible_students(_current_user())
    student_map = {s.id: s.full_name() for s in students}
    all_categories = QuestionCategory.query.order_by(
        QuestionCategory.order_index, QuestionCategory.name
    ).all()

    return render_template(
        "exercise_manager.html",
        items=page_items,
        total=total,
        page=page,
        per_page=PER_PAGE,
        students=students,
        student_map=student_map,
        all_categories=all_categories,
        domain_choices=DOMAIN_CHOICES,
        difficulty_choices=_display_constants()[0],
        difficulty_display=_display_constants()[1],
        filter_type=ex_type,
        filter_q=q,
        filter_domain=domain,
        filter_difficulty=difficulty,
        filter_student_id=student_id_raw,
        filter_date_from=date_from_raw,
        filter_date_to=date_to_raw,
    )


@bp.route("/prepared-questions/<int:question_id>/edit",
    methods=["GET", "POST"],
)
@_parent_required
def edit_prepared_question(question_id: int):
    question = PreparedExerciseQuestion.query.get_or_404(question_id)
    categories = QuestionCategory.query.order_by(
        QuestionCategory.order_index, QuestionCategory.name
    ).all()

    if request.method == "POST":
        prompt = sanitize_text_input(request.form.get("prompt", ""))
        answer = sanitize_text_input(request.form.get("answer", ""))
        category_code = (
            request.form.get("category", question.category_code) or ""
        ).strip() or question.category_code

        valid, msg = validate_question_content(prompt, answer)
        if not valid:
            flash(msg, "danger")
            return render_template(
                "edit_prepared_question.html",
                question=question,
                categories=categories,
                form_data={"prompt": prompt, "answer": answer, "category": category_code},
            )

        known_codes = {c.code for c in categories}
        if category_code not in known_codes:
            category_code = question.category_code

        question.prompt = prompt
        question.answer = answer
        question.category_code = category_code
        db.session.commit()

        flash("Question préparée modifiée avec succès.", "success")
        return redirect(url_for("parents.list_all_exercises"))

    return render_template(
        "edit_prepared_question.html",
        question=question,
        categories=categories,
        form_data=None,
    )


@bp.route("/exercise-items/<int:item_id>/edit",
    methods=["GET", "POST"],
)
@_parent_required
def edit_exercise_item(item_id: int):
    item = ExerciseItem.query.get_or_404(item_id)
    categories = QuestionCategory.query.order_by(
        QuestionCategory.order_index, QuestionCategory.name
    ).all()

    if request.method == "POST":
        prompt = sanitize_text_input(request.form.get("prompt", ""))
        answer = sanitize_text_input(request.form.get("answer", ""))
        category_code = (request.form.get("category", "") or "").strip()
        difficulty_raw = (request.form.get("difficulty", "") or "").strip()
        is_active = "is_active" in request.form

        valid, msg = validate_question_content(prompt, answer)
        if not valid:
            flash(msg, "danger")
            return render_template(
                "edit_exercise_item.html",
                item=item,
                categories=categories,
                difficulty_choices=_display_constants()[0],
                form_data={
                    "prompt": prompt,
                    "answer": answer,
                    "category": category_code,
                    "difficulty": difficulty_raw,
                    "is_active": is_active,
                },
            )

        cat = QuestionCategory.query.filter_by(code=category_code).first()
        if cat:
            item.category_id = cat.id
        valid_diffs = set(DIFFICULTY_LEVELS) | {"any"}
        if difficulty_raw in valid_diffs:
            item.difficulty = difficulty_raw
        item.prompt = prompt
        item.answer = answer
        item.is_active = is_active
        db.session.commit()

        flash("Exercice de la banque modifié avec succès.", "success")
        return redirect(url_for("parents.list_all_exercises"))

    return render_template(
        "edit_exercise_item.html",
        item=item,
        categories=categories,
        difficulty_choices=_display_constants()[0],
        form_data=None,
    )


@bp.route("/exercises/bulk-edit", methods=["POST"])
@_parent_required
def bulk_edit_exercises():
    from ...services.imports import apply_bulk_change, parse_batch_selection

    bulk_field = (request.form.get("bulk_field") or "").strip()
    bulk_value = (request.form.get("bulk_value") or "").strip()

    if bulk_field not in ("category", "difficulty"):
        flash("Champ de modification invalide.", "danger")
        return redirect(url_for("parents.list_all_exercises"))

    valid_cat_codes = {c.code for c in QuestionCategory.query.all()}
    valid_diffs = set(DIFFICULTY_LEVELS) | {"any"}

    if bulk_field == "category" and bulk_value not in valid_cat_codes:
        flash("Catégorie invalide.", "danger")
        return redirect(url_for("parents.list_all_exercises"))
    if bulk_field == "difficulty" and bulk_value not in valid_diffs:
        flash("Niveau de difficulté invalide.", "danger")
        return redirect(url_for("parents.list_all_exercises"))

    items_to_edit = parse_batch_selection(request.form)

    if not items_to_edit:
        flash("Aucun exercice sélectionné.", "warning")
        return redirect(url_for("parents.list_all_exercises", **_preserve_filters(request.form)))

    updated = apply_bulk_change(
        items_to_edit,
        bulk_field,
        bulk_value,
        valid_category_codes=valid_cat_codes if bulk_field == "category" else None,
    )

    flash(f"{updated} exercice(s) modifié(s).", "success")
    return redirect(url_for("parents.list_all_exercises", **_preserve_filters(request.form)))


@bp.route("/exercise-items/<int:item_id>/toggle-active", methods=["POST"])
@_parent_required
def toggle_exercise_item_active(item_id: int):
    item = ExerciseItem.query.get_or_404(item_id)
    item.is_active = not item.is_active
    db.session.commit()
    flash("Exercice réactivé." if item.is_active else "Exercice désactivé.", "success" if item.is_active else "info")
    return redirect(url_for("parents.list_all_exercises"))


@bp.route("/exercises/batch-edit", methods=["POST"])
@_parent_required
def batch_edit_exercises():
    from ...services.imports import parse_batch_selection

    items_raw = parse_batch_selection(request.form)

    if not items_raw:
        flash("Aucun exercice sélectionné.", "warning")
        return redirect(url_for("parents.list_all_exercises", **_preserve_filters(request.form)))

    exercises = []
    for item_type, item_id in items_raw:
        if item_type == "session":
            ex = SessionExercise.query.get(item_id)
            if ex:
                sess = ex.session
                exercises.append({
                    "index": len(exercises),
                    "type": "session",
                    "id": ex.id,
                    "prompt": ex.prompt,
                    "answer": ex.correct_answer,
                    "category_code": ex.category,
                    "difficulty": None,
                    "context": f"Session du {sess.started_at.strftime('%d/%m/%Y')}" if sess else "",
                })
        elif item_type == "prepared":
            ex = PreparedExerciseQuestion.query.get(item_id)
            if ex:
                es = ex.exercise_set
                exercises.append({
                    "index": len(exercises),
                    "type": "prepared",
                    "id": ex.id,
                    "prompt": ex.prompt,
                    "answer": ex.answer,
                    "category_code": ex.category_code,
                    "difficulty": None,
                    "context": f"Série : {es.title}" if es else "",
                })
        elif item_type == "bank":
            ex = ExerciseItem.query.get(item_id)
            if ex:
                exercises.append({
                    "index": len(exercises),
                    "type": "bank",
                    "id": ex.id,
                    "prompt": ex.prompt,
                    "answer": ex.answer,
                    "category_code": ex.category.code if ex.category else "",
                    "difficulty": ex.difficulty,
                    "context": "",
                })

    if not exercises:
        flash("Les exercices sélectionnés sont introuvables.", "warning")
        return redirect(url_for("parents.list_all_exercises"))

    categories = QuestionCategory.query.order_by(
        QuestionCategory.order_index, QuestionCategory.name
    ).all()
    back_url = url_for("parents.list_all_exercises", **_preserve_filters(request.form))

    return render_template(
        "batch_edit_exercises.html",
        exercises=exercises,
        categories=categories,
        difficulty_choices=_display_constants()[0],
        difficulty_display=_display_constants()[1],
        back_url=back_url,
    )


@bp.route("/exercises/batch-save", methods=["POST"])
@_parent_required
def batch_save_exercises():
    back_url = request.form.get("back_url") or url_for("parents.list_all_exercises")
    if not is_safe_url(back_url):
        back_url = url_for("parents.list_all_exercises")

    categories = QuestionCategory.query.all()
    cat_by_code = {c.code: c for c in categories}
    valid_cat_codes = set(cat_by_code.keys())
    valid_diffs = set(DIFFICULTY_LEVELS) | {"any"}

    updated = 0
    errors = []
    i = 0
    while True:
        item_type = request.form.get(f"exercise_{i}_type")
        item_id_raw = request.form.get(f"exercise_{i}_id")
        if item_type is None and item_id_raw is None:
            break
        try:
            item_id = int(item_id_raw)
        except (TypeError, ValueError):
            i += 1
            continue

        prompt = sanitize_text_input(request.form.get(f"exercise_{i}_prompt", ""))
        answer = sanitize_text_input(request.form.get(f"exercise_{i}_answer", ""))
        category_code = (request.form.get(f"exercise_{i}_category") or "").strip()
        difficulty_raw = (request.form.get(f"exercise_{i}_difficulty") or "").strip()

        valid, msg = validate_question_content(prompt, answer)
        if not valid:
            errors.append(f"Q{i + 1} : {msg}")
            i += 1
            continue

        if item_type == "session":
            ex = SessionExercise.query.get(item_id)
            if ex:
                ex.prompt = prompt
                ex.correct_answer = answer
                if category_code in valid_cat_codes:
                    ex.category = category_code
                updated += 1
        elif item_type == "prepared":
            ex = PreparedExerciseQuestion.query.get(item_id)
            if ex:
                ex.prompt = prompt
                ex.answer = answer
                if category_code in valid_cat_codes:
                    ex.category_code = category_code
                updated += 1
        elif item_type == "bank":
            ex = ExerciseItem.query.get(item_id)
            if ex:
                ex.prompt = prompt
                ex.answer = answer
                cat = cat_by_code.get(category_code)
                if cat:
                    ex.category_id = cat.id
                if difficulty_raw in valid_diffs:
                    ex.difficulty = difficulty_raw
                updated += 1

        i += 1

    db.session.commit()

    for err in errors:
        flash(err, "warning")
    if updated:
        flash(f"{updated} exercice(s) sauvegardé(s).", "success")

    return redirect(back_url)
