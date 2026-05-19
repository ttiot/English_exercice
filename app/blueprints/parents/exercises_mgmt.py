"""Gestionnaire unifié d'exercices : liste paginée + filtres, édition unitaire (préparé / banque), opérations bulk (bulk-edit, batch-edit, batch-save, toggle-active)."""

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
