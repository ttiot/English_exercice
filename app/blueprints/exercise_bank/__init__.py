"""Blueprint ``exercise_bank`` : exploration de la banque d'exercices
(procéduraux + items personnalisés + pool IA) et opérations CRUD parent.

Préfixe : ``/exercise-bank``.
"""

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from ...exercise_factory import (
    generate_exercises_for_categories,
    normalize_difficulty,
)
from ...extensions import db
from ...models import AIGeneratedExercise, ExerciseItem, QuestionCategory, Student
from ...services.auth import _login_required, _parent_required
from ...services.curriculum import (
    DOMAIN_CHOICES,
    _build_prerequisite_map,
    _filter_categories,
)
from ...validators import sanitize_text_input, validate_question_content


bp = Blueprint("exercise_bank", __name__, url_prefix="/exercise-bank")


def _constants():
    from ...routes import CEFR_LEVELS, GRADE_LEVELS, TRIMESTER_CHOICES

    return CEFR_LEVELS, GRADE_LEVELS, TRIMESTER_CHOICES


@bp.route("")
@_login_required
def exercise_bank():
    cefr_levels, grade_levels, trimester_choices = _constants()
    domain = request.args.get("domain") or ""
    cefr = request.args.get("cefr") or ""
    grade = request.args.get("grade") or ""
    trimester = request.args.get("trimester") or ""
    categories = _filter_categories(domain, cefr, grade, trimester)
    prereq_map = _build_prerequisite_map()
    exercise_items = []
    if categories:
        category_ids = [category.id for category in categories]
        exercise_items = (
            ExerciseItem.query.filter(ExerciseItem.category_id.in_(category_ids))
            .order_by(ExerciseItem.created_at.desc())
            .limit(50)
            .all()
        )

    return render_template(
        "exercise_bank.html",
        categories=categories,
        domain_choices=DOMAIN_CHOICES,
        cefr_levels=cefr_levels,
        grade_levels=grade_levels,
        trimester_choices=trimester_choices,
        selected_domain=domain,
        selected_cefr=cefr,
        selected_grade=grade,
        selected_trimester=trimester,
        prereq_map=prereq_map,
        exercise_items=exercise_items,
    )


@bp.route("/generate", methods=["POST"])
@_login_required
def generate_exercises_from_bank():
    cefr_levels, grade_levels, trimester_choices = _constants()
    domain = request.form.get("domain") or ""
    cefr = request.form.get("cefr") or ""
    grade = request.form.get("grade") or ""
    trimester = request.form.get("trimester") or ""
    difficulty = normalize_difficulty(request.form.get("difficulty"))
    category_code = request.form.get("category_code") or ""
    try:
        quantity = int(request.form.get("quantity", 10))
    except ValueError:
        quantity = 10
    quantity = max(1, min(30, quantity))

    categories = _filter_categories(domain, cefr, grade, trimester)
    if category_code and category_code != "all":
        categories = [category for category in categories if category.code == category_code]

    category_codes = [category.code for category in categories]
    generated = generate_exercises_for_categories(
        category_codes, quantity, difficulty=difficulty
    ) if category_codes else []
    prereq_map = _build_prerequisite_map()
    exercise_items = []
    if categories:
        category_ids = [category.id for category in categories]
        exercise_items = (
            ExerciseItem.query.filter(ExerciseItem.category_id.in_(category_ids))
            .order_by(ExerciseItem.created_at.desc())
            .limit(50)
            .all()
        )

    return render_template(
        "exercise_bank.html",
        categories=categories,
        domain_choices=DOMAIN_CHOICES,
        cefr_levels=cefr_levels,
        grade_levels=grade_levels,
        trimester_choices=trimester_choices,
        selected_domain=domain,
        selected_cefr=cefr,
        selected_grade=grade,
        selected_trimester=trimester,
        selected_difficulty=difficulty,
        selected_category=category_code,
        quantity=quantity,
        prereq_map=prereq_map,
        generated_exercises=generated,
        exercise_items=exercise_items,
    )


@bp.route("/items", methods=["POST"])
@_parent_required
def add_exercise_item():
    category_code = request.form.get("category_code", "").strip()
    difficulty_raw = request.form.get("difficulty", "").strip()
    difficulty = difficulty_raw if difficulty_raw == "any" else normalize_difficulty(difficulty_raw)
    prompt = sanitize_text_input(request.form.get("prompt", ""))
    answer = sanitize_text_input(request.form.get("answer", ""))

    category = QuestionCategory.query.filter_by(code=category_code).first()
    if not category:
        flash("Catégorie invalide.", "danger")
        return redirect(url_for("exercise_bank.exercise_bank"))

    if not prompt or not answer:
        flash("La question et la réponse sont obligatoires.", "danger")
        return redirect(url_for("exercise_bank.exercise_bank"))

    content_valid, content_message = validate_question_content(prompt, answer)
    if not content_valid:
        flash(f"Question invalide : {content_message}", "danger")
        return redirect(url_for("exercise_bank.exercise_bank"))

    db.session.add(
        ExerciseItem(
            category_id=category.id,
            difficulty=difficulty,
            prompt=prompt,
            answer=answer,
            is_active=True,
        )
    )
    db.session.commit()
    flash("Question ajoutée dans la banque.", "success")
    return redirect(url_for("exercise_bank.exercise_bank"))


@bp.route("/ai")
@_parent_required
def ai_exercise_pool():
    from sqlalchemy import desc

    page = max(int(request.args.get("page", 1) or 1), 1)
    per_page = 25
    show_disabled = request.args.get("disabled") == "1"

    query = AIGeneratedExercise.query
    if not show_disabled:
        query = query.filter(AIGeneratedExercise.is_disabled.is_(False))
    query = query.order_by(desc(AIGeneratedExercise.created_at))

    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()

    student_lookup = {
        s.id: s
        for s in Student.query.filter(
            Student.id.in_({i.student_id for i in items if i.student_id})
        ).all()
    }

    return render_template(
        "ai_pool.html",
        items=items,
        student_lookup=student_lookup,
        page=page,
        per_page=per_page,
        total=total,
        show_disabled=show_disabled,
    )


@bp.route("/ai/<int:item_id>/toggle", methods=["POST"])
@_parent_required
def toggle_ai_exercise(item_id: int):
    item = AIGeneratedExercise.query.get_or_404(item_id)
    item.is_disabled = not item.is_disabled
    db.session.commit()
    flash(
        "Exercice IA désactivé." if item.is_disabled else "Exercice IA réactivé.",
        "info",
    )
    return redirect(url_for("exercise_bank.ai_exercise_pool"))


@bp.route("/items/<int:item_id>/delete", methods=["POST"])
@_parent_required
def delete_exercise_item(item_id: int):
    item = ExerciseItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    flash("Question supprimée.", "success")
    return redirect(url_for("exercise_bank.exercise_bank"))
