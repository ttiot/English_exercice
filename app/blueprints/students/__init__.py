"""Blueprint ``students`` : CRUD du profil élève + démarrage de session de
pratique (la création de session vit sous ``/students/<id>/sessions/new``,
donc côté élève).

Préfixe : ``/students``.
"""

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.utils import secure_filename

from ...exercise_factory import (
    AVAILABLE_CATEGORIES,
    DIFFICULTY_LEVELS,
    ExercisePrompt,
    generate_default_exercises,
    generate_exercises_for_categories,
    normalize_difficulty,
)
from ...extensions import db
from ...models import (
    Badge,
    PracticeSession,
    PreparedExerciseSet,
    QuestionCategory,
    ReviewPlan,
    SessionExercise,
    Student,
    StudentBadge,
)
from ...services.analytics import (
    _student_recurring_errors,
    _student_theme_summary,
)
from ...services.answer_validation import _session_exercise_kwargs
from ...services.auth import (
    _current_user,
    _get_student_or_404,
    _login_required,
    _parent_required,
)
from ...services.curriculum import (
    DOMAIN_CHOICES,
    _build_prerequisite_map,
    _category_in_target,
    _category_priority,
    _domain_list,
    _is_category_unlocked,
    _load_progress_map,
    _parse_domain_list,
    _recommend_difficulty,
)
from ...services.gamification import (
    _compute_activity_heatmap,
    _compute_global_streak,
    _compute_weekly_progress,
    _compute_xp_and_level,
    _current_week_range,
    _get_weekly_goal,
    _review_interval_days,
)
from ...validators import (
    sanitize_text_input,
    validate_age,
    validate_email,
    validate_goals,
    validate_name,
    validate_password,
)


bp = Blueprint("students", __name__, url_prefix="/students")


def _validate_image_file(file):
    from ...routes import validate_image_file

    return validate_image_file(file)


def _delete_avatar_file(filename):
    from ...routes import _delete_avatar_file as impl

    return impl(filename)


def _constants():
    from ...routes import (
        CEFR_LEVELS,
        DIFFICULTY_CHOICES,
        DIFFICULTY_DISPLAY,
        GRADE_LEVELS,
        SESSION_TYPE_LABELS,
        TRIMESTER_CHOICES,
    )

    return {
        "cefr_levels": CEFR_LEVELS,
        "grade_levels": GRADE_LEVELS,
        "trimester_choices": TRIMESTER_CHOICES,
        "difficulty_choices": DIFFICULTY_CHOICES,
        "difficulty_labels": DIFFICULTY_DISPLAY,
        "session_type_labels": SESSION_TYPE_LABELS,
    }


@bp.route("/new", methods=["GET", "POST"])
@_parent_required
def create_student():
    consts = _constants()

    def _render_with_form_data(form_data: Dict[str, str], selected_domains: List[str]):
        return render_template(
            "student_form.html",
            form_data=form_data,
            selected_domains=selected_domains,
            cefr_levels=consts["cefr_levels"],
            grade_levels=consts["grade_levels"],
            trimester_choices=consts["trimester_choices"],
            domain_choices=DOMAIN_CHOICES,
        )

    if request.method == "POST":
        first_name = sanitize_text_input(request.form.get("first_name", ""))
        last_name = sanitize_text_input(request.form.get("last_name", "")) or None
        email_raw = sanitize_text_input(request.form.get("email", "")).lower()
        age_raw = request.form.get("age", "").strip()
        goals = sanitize_text_input(request.form.get("goals", "")) or None
        target_cefr_level = request.form.get("target_cefr_level") or None
        target_grade = request.form.get("target_grade") or None
        target_trimester_raw = request.form.get("target_trimester") or ""
        interests = sanitize_text_input(request.form.get("interests", "")) or None
        preferred_domains = _parse_domain_list(request.form.getlist("preferred_domains"))
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        form_data = {
            "first_name": first_name,
            "last_name": last_name or "",
            "email": email_raw,
            "age": age_raw,
            "goals": goals or "",
            "target_cefr_level": target_cefr_level or "",
            "target_grade": target_grade or "",
            "target_trimester": target_trimester_raw or "",
            "interests": interests or "",
        }
        selected_domains = request.form.getlist("preferred_domains")

        if not validate_name(first_name):
            flash("Le prénom contient des caractères invalides ou est trop long.", "danger")
            return _render_with_form_data(form_data, selected_domains)

        if last_name and not validate_name(last_name):
            flash("Le nom de famille contient des caractères invalides ou est trop long.", "danger")
            return _render_with_form_data(form_data, selected_domains)

        if not validate_email(email_raw):
            flash("L'adresse e-mail n'est pas valide.", "danger")
            return _render_with_form_data(form_data, selected_domains)

        if Student.query.filter_by(email=email_raw).first():
            flash("Cette adresse e-mail est déjà utilisée.", "danger")
            return _render_with_form_data(form_data, selected_domains)

        password_valid, password_message = validate_password(password)
        if not password_valid:
            flash(password_message, "danger")
            return _render_with_form_data(form_data, selected_domains)

        if password != password_confirm:
            flash("La confirmation du mot de passe ne correspond pas.", "danger")
            return _render_with_form_data(form_data, selected_domains)

        age_value = validate_age(age_raw)
        if age_raw and age_value is None:
            flash("L'âge doit être un nombre valide entre 3 et 120 ans.", "danger")
            return _render_with_form_data(form_data, selected_domains)

        if goals and not validate_goals(goals):
            flash("Les objectifs contiennent du contenu invalide.", "danger")
            return _render_with_form_data(form_data, selected_domains)

        if target_cefr_level and target_cefr_level not in consts["cefr_levels"]:
            flash("Le niveau CECRL est invalide.", "danger")
            return _render_with_form_data(form_data, selected_domains)

        if target_grade and target_grade not in consts["grade_levels"]:
            flash("Le niveau scolaire est invalide.", "danger")
            return _render_with_form_data(form_data, selected_domains)

        target_trimester = None
        if target_trimester_raw:
            try:
                target_trimester = int(target_trimester_raw)
            except ValueError:
                flash("Le trimestre est invalide.", "danger")
                return _render_with_form_data(form_data, selected_domains)
            if target_trimester not in consts["trimester_choices"]:
                flash("Le trimestre est invalide.", "danger")
                return _render_with_form_data(form_data, selected_domains)

        avatar_file = request.files.get("avatar")
        avatar_filename: Optional[str] = None
        if avatar_file and avatar_file.filename:
            if not _validate_image_file(avatar_file):
                flash("Format d'image non pris en charge ou fichier invalide.", "danger")
                return _render_with_form_data(form_data, selected_domains)

            sanitized = secure_filename(avatar_file.filename)
            extension = sanitized.rsplit(".", 1)[-1].lower() if "." in sanitized else ""
            avatar_filename = f"{uuid4().hex}.{extension}"
            destination = Path(current_app.config["UPLOAD_FOLDER"]) / avatar_filename
            avatar_file.save(destination)

        student = Student(
            first_name=first_name,
            last_name=last_name,
            email=email_raw,
            age=age_value,
            goals=goals,
            target_cefr_level=target_cefr_level,
            target_grade=target_grade,
            target_trimester=target_trimester,
            interests=interests,
            preferred_domains=preferred_domains or None,
            avatar_filename=avatar_filename,
            role="student",
        )
        student.set_password(password)
        db.session.add(student)
        db.session.commit()

        creator = _current_user()
        if creator and creator.is_parent():
            creator.managed_students.append(student)
            db.session.commit()

        flash("Profil élève créé avec succès !", "success")
        return redirect(url_for("students.view_student", student_id=student.id))

    return render_template(
        "student_form.html",
        form_data={},
        selected_domains=[],
        cefr_levels=consts["cefr_levels"],
        grade_levels=consts["grade_levels"],
        trimester_choices=consts["trimester_choices"],
        domain_choices=DOMAIN_CHOICES,
    )


@bp.route("/<int:student_id>")
@_login_required
def view_student(student_id: int):
    student = _get_student_or_404(student_id)
    user = _current_user()

    parent_ok = user.is_parent() or user.is_admin()
    student_ok = user.id == student.id
    if not (student_ok or parent_ok):
        flash("Accès refusé pour ce profil.", "danger")
        return redirect(url_for("auth.index"))

    sessions = (
        PracticeSession.query.filter_by(student_id=student.id)
        .order_by(PracticeSession.started_at.desc())
        .all()
    )

    categories = (
        QuestionCategory.query.order_by(QuestionCategory.order_index.asc().nullslast(), QuestionCategory.name)
        .all()
    )
    category_lookup = {category.code: category.name for category in categories}
    progress_map = _load_progress_map(student.id)

    progress = []
    for category in categories:
        progress_entry = progress_map.get(category.id)
        total = progress_entry.total_attempts if progress_entry else 0
        correct = progress_entry.correct_attempts if progress_entry else 0
        rate = progress_entry.mastery if progress_entry else 0.0
        next_review = None
        if progress_entry and progress_entry.last_practiced:
            interval_days = _review_interval_days(progress_entry.mastery or 0.0)
            next_review = progress_entry.last_practiced + timedelta(days=interval_days)
        progress.append(
            {
                "code": category.code,
                "label": category_lookup.get(category.code, category.code.replace("_", " ").title()),
                "correct": correct,
                "total": total,
                "rate": rate,
                "last_practiced": progress_entry.last_practiced if progress_entry else None,
                "next_review": next_review,
                "domain": category.domain,
            }
        )
    if not any(item["total"] for item in progress):
        progress = []

    upcoming_set = (
        PreparedExerciseSet.query.filter_by(is_used=False, student_id=student.id)
        .order_by(PreparedExerciseSet.created_at.asc())
        .first()
    )
    if not upcoming_set:
        upcoming_set = (
            PreparedExerciseSet.query.filter_by(is_used=False, student_id=None)
            .order_by(PreparedExerciseSet.created_at.asc())
            .first()
        )

    week_start = _current_week_range()[0]
    weekly_goal = _get_weekly_goal(student.id, week_start)
    weekly_progress = _compute_weekly_progress(student, week_start)
    review_plans = (
        ReviewPlan.query.filter(
            ReviewPlan.student_id == student.id,
            ReviewPlan.completed.is_(False),
            ReviewPlan.due_date >= date.today(),
        )
        .order_by(ReviewPlan.due_date.asc())
        .limit(8)
        .all()
    )
    badges = Badge.query.order_by(Badge.name).all()
    earned_badge_ids = {
        item.badge_id for item in StudentBadge.query.filter_by(student_id=student.id).all()
    }
    badge_status = []
    for badge in badges:
        earned = badge.id in earned_badge_ids
        prog = progress_map.get(badge.category_id) if badge.category_id else None
        current_mastery = prog.mastery if prog else 0.0
        current_streak = prog.correct_streak if prog else 0
        mastery_pct = min(100, int(current_mastery / max(0.01, badge.min_mastery) * 100)) if not earned else 100
        badge_status.append({
            "badge": badge,
            "earned": earned,
            "current_mastery": round(current_mastery, 1),
            "mastery_pct": mastery_pct,
            "current_streak": current_streak,
            "streak_done": current_streak >= badge.min_streak,
        })
    badge_status.sort(key=lambda b: (0 if b["earned"] else 1, -b["mastery_pct"]))

    theme_summary = _student_theme_summary(student.id) if parent_ok else []
    recurring_errors = _student_recurring_errors(student.id) if parent_ok else []
    xp_data = _compute_xp_and_level(sessions)
    global_streak = _compute_global_streak(sessions)
    activity_heatmap = _compute_activity_heatmap(sessions)
    resume_session = (
        PracticeSession.query.filter(
            PracticeSession.student_id == student.id,
            PracticeSession.completed_at.is_(None),
            PracticeSession.started_at >= datetime.utcnow() - timedelta(days=7),
        )
        .order_by(PracticeSession.started_at.desc())
        .first()
    )

    return render_template(
        "student_detail.html",
        student=student,
        sessions=sessions,
        progress=progress,
        upcoming_set=upcoming_set,
        category_lookup=category_lookup,
        can_manage=parent_ok or student_ok,
        parent_ok=parent_ok,
        difficulty_labels=_constants()["difficulty_labels"],
        weekly_goal=weekly_goal,
        weekly_progress=weekly_progress,
        week_start=week_start,
        review_plans=review_plans,
        badge_status=badge_status,
        theme_summary=theme_summary,
        recurring_errors=recurring_errors,
        xp_data=xp_data,
        global_streak=global_streak,
        activity_heatmap=activity_heatmap,
        resume_session=resume_session,
    )


@bp.route("/<int:student_id>/settings", methods=["GET", "POST"])
@_login_required
def manage_student(student_id: int):
    student = _get_student_or_404(student_id)
    consts = _constants()

    user = _current_user()
    parent_ok = user.is_parent() or user.is_admin()
    student_ok = user.id == student.id
    if not (parent_ok or student_ok):
        flash("Accès refusé.", "danger")
        return redirect(url_for("auth.index"))

    if request.method == "POST":
        action = request.form.get("action", "profile")

        if action == "password":
            current_password = request.form.get("current_password", "").strip()
            new_password = request.form.get("new_password", "").strip()
            confirm_password = request.form.get("confirm_password", "").strip()

            if len(new_password) < 8:
                flash(
                    "Le nouveau mot de passe doit contenir au moins 8 caractères.",
                    "danger",
                )
                return redirect(url_for("students.manage_student", student_id=student.id))

            if new_password != confirm_password:
                flash("La confirmation du mot de passe ne correspond pas.", "danger")
                return redirect(url_for("students.manage_student", student_id=student.id))

            if not parent_ok and not student.check_password(current_password):
                flash("L'ancien mot de passe est incorrect.", "danger")
                return redirect(url_for("students.manage_student", student_id=student.id))

            student.set_password(new_password)
            db.session.commit()
            flash("Mot de passe mis à jour avec succès.", "success")
            return redirect(url_for("students.manage_student", student_id=student.id))

        # Default to profile update
        first_name = sanitize_text_input(request.form.get("first_name", ""))
        last_name = sanitize_text_input(request.form.get("last_name", ""))
        email_raw = sanitize_text_input(request.form.get("email", "")).lower()
        goals = sanitize_text_input(request.form.get("goals", ""))
        age_raw = request.form.get("age", "").strip()
        target_cefr_level = request.form.get("target_cefr_level") or None
        target_grade = request.form.get("target_grade") or None
        target_trimester_raw = request.form.get("target_trimester") or ""
        interests = sanitize_text_input(request.form.get("interests", "")) or None
        preferred_domains = _parse_domain_list(request.form.getlist("preferred_domains"))
        remove_avatar = request.form.get("remove_avatar") == "on"

        if not first_name:
            flash("Le prénom est obligatoire.", "danger")
            return redirect(url_for("students.manage_student", student_id=student.id))

        if not email_raw:
            flash("L'adresse e-mail est obligatoire.", "danger")
            return redirect(url_for("students.manage_student", student_id=student.id))

        existing_email = Student.query.filter_by(email=email_raw).first()
        if existing_email and existing_email.id != student.id:
            flash("Cette adresse e-mail est déjà utilisée.", "danger")
            return redirect(url_for("students.manage_student", student_id=student.id))

        try:
            age_value = int(age_raw) if age_raw else None
        except ValueError:
            flash("L'âge doit être un nombre.", "danger")
            return redirect(url_for("students.manage_student", student_id=student.id))

        if goals and not validate_goals(goals):
            flash("Les objectifs contiennent du contenu invalide.", "danger")
            return redirect(url_for("students.manage_student", student_id=student.id))

        if target_cefr_level and target_cefr_level not in consts["cefr_levels"]:
            flash("Le niveau CECRL est invalide.", "danger")
            return redirect(url_for("students.manage_student", student_id=student.id))

        if target_grade and target_grade not in consts["grade_levels"]:
            flash("Le niveau scolaire est invalide.", "danger")
            return redirect(url_for("students.manage_student", student_id=student.id))

        target_trimester = None
        if target_trimester_raw:
            try:
                target_trimester = int(target_trimester_raw)
            except ValueError:
                flash("Le trimestre est invalide.", "danger")
                return redirect(url_for("students.manage_student", student_id=student.id))
            if target_trimester not in consts["trimester_choices"]:
                flash("Le trimestre est invalide.", "danger")
                return redirect(url_for("students.manage_student", student_id=student.id))

        avatar_file = request.files.get("avatar")
        new_avatar_filename: Optional[str] = None
        if avatar_file and avatar_file.filename:
            if not _validate_image_file(avatar_file):
                flash("Format d'image non pris en charge ou fichier invalide.", "danger")
                return redirect(url_for("students.manage_student", student_id=student.id))

            sanitized = secure_filename(avatar_file.filename)
            extension = sanitized.rsplit(".", 1)[-1].lower() if "." in sanitized else ""
            new_avatar_filename = f"{uuid4().hex}.{extension}"
            destination = Path(current_app.config["UPLOAD_FOLDER"]) / new_avatar_filename
            avatar_file.save(destination)

        if remove_avatar and student.avatar_filename:
            _delete_avatar_file(student.avatar_filename)
            student.avatar_filename = None

        if new_avatar_filename:
            if student.avatar_filename and student.avatar_filename != new_avatar_filename:
                _delete_avatar_file(student.avatar_filename)
            student.avatar_filename = new_avatar_filename

        student.first_name = first_name
        student.last_name = last_name or None
        student.email = email_raw
        student.goals = goals or None
        student.age = age_value
        student.target_cefr_level = target_cefr_level
        student.target_grade = target_grade
        student.target_trimester = target_trimester
        student.interests = interests
        student.preferred_domains = preferred_domains or None

        db.session.commit()
        flash("Profil mis à jour.", "success")
        return redirect(url_for("students.manage_student", student_id=student.id))

    return render_template(
        "student_settings.html",
        student=student,
        parent_ok=parent_ok,
        cefr_levels=consts["cefr_levels"],
        grade_levels=consts["grade_levels"],
        trimester_choices=consts["trimester_choices"],
        domain_choices=DOMAIN_CHOICES,
        selected_domains=_domain_list(student.preferred_domains),
    )


@bp.route("/<int:student_id>/sessions/new", methods=["GET", "POST"])
@_login_required
def start_session(student_id: int):
    student = _get_student_or_404(student_id)
    user = _current_user()
    if not (user.id == student.id or user.is_parent() or user.is_admin()):
        flash("Accès refusé.", "danger")
        return redirect(url_for("students.view_student", student_id=student.id))

    consts = _constants()

    if request.method == "POST":
        session_mode = request.form.get("session_mode", "practice")
        difficulty_choice = request.form.get("difficulty", DIFFICULTY_LEVELS[0])
        adaptive_difficulty = "1" in request.form.getlist("adaptive_difficulty")
        use_skill_path = "1" in request.form.getlist("skill_path")
        difficulty_value = (
            _recommend_difficulty(student) if adaptive_difficulty else normalize_difficulty(difficulty_choice)
        )
        try:
            time_limit = request.form.get("time_limit")
            time_limit_value = int(time_limit) if time_limit else None
        except ValueError:
            flash("La durée doit être un nombre de minutes.", "danger")
            return redirect(url_for("students.start_session", student_id=student.id))

        quantity = request.form.get("question_count")
        try:
            question_count = int(quantity) if quantity else 20
        except ValueError:
            question_count = 20

        session_type = "practice"
        if session_mode == "challenge_10":
            session_type = "challenge"
            time_limit_value = 10
        elif session_mode == "challenge_15":
            session_type = "challenge"
            time_limit_value = 15
        elif session_mode == "control":
            session_type = "control"
            if not time_limit_value:
                time_limit_value = 20
        elif session_mode == "ai_custom":
            session_type = "ai_custom"

        # Mode IA : on bypasse les parcours préparés / procéduraux.
        if session_type == "ai_custom":
            from ...services.ai_generator import (
                generate_exercises as ai_generate_exercises,
                get_openai_client,
                is_budget_exceeded,
            )

            student_prompt = sanitize_text_input(request.form.get("student_prompt", ""))
            if not student_prompt or len(student_prompt) < 5:
                flash(
                    "Décris en quelques mots le sujet sur lequel tu veux travailler "
                    "(au moins 5 caractères).",
                    "warning",
                )
                return redirect(url_for("students.start_session", student_id=student.id))
            if len(student_prompt) > 500:
                student_prompt = student_prompt[:500]

            client, _ = get_openai_client()
            if not client:
                flash(
                    "OpenAI n'est pas configuré. Demande à l'administrateur "
                    "d'activer le service IA.",
                    "danger",
                )
                return redirect(url_for("students.start_session", student_id=student.id))
            if is_budget_exceeded():
                flash(
                    "Le budget mensuel IA est atteint. Réessaie le mois prochain "
                    "ou demande à l'administrateur d'augmenter le plafond.",
                    "warning",
                )
                return redirect(url_for("students.start_session", student_id=student.id))

            ai_pairs = ai_generate_exercises(
                student_prompt=student_prompt,
                count=question_count,
                difficulty=difficulty_value,
                student_id=student.id,
            )
            if not ai_pairs:
                flash(
                    "Désolé, l'IA n'a pas pu générer d'exercices pour ce thème. "
                    "Reformule ou réessaie plus tard.",
                    "danger",
                )
                return redirect(url_for("students.start_session", student_id=student.id))

            session_obj = PracticeSession(
                student_id=student.id,
                time_limit_minutes=time_limit_value,
                time_limit_seconds=(time_limit_value * 60) if time_limit_value else None,
                total_questions=len(ai_pairs),
                difficulty=difficulty_value,
                session_type="ai_custom",
                instructions_fr=student_prompt,
            )
            db.session.add(session_obj)
            db.session.flush()
            for index, (exercise, pool_row) in enumerate(ai_pairs):
                db.session.add(
                    SessionExercise(
                        session_id=session_obj.id,
                        display_order=index,
                        **_session_exercise_kwargs(
                            exercise, source="ai", ai_exercise_id=pool_row.id
                        ),
                    )
                )
                pool_row.times_used = (pool_row.times_used or 0) + 1
            db.session.commit()
            return redirect(url_for("sessions.play_session", session_id=session_obj.id))

        session_obj = PracticeSession(
            student_id=student.id,
            time_limit_minutes=time_limit_value,
            time_limit_seconds=(time_limit_value * 60) if time_limit_value else None,
            total_questions=question_count,
            difficulty=difficulty_value,
            session_type=session_type,
        )
        db.session.add(session_obj)
        db.session.flush()

        targeted_set = (
            PreparedExerciseSet.query.filter_by(is_used=False, student_id=student.id)
            .order_by(PreparedExerciseSet.created_at.asc())
            .first()
        )
        general_set = (
            PreparedExerciseSet.query.filter_by(is_used=False, student_id=None)
            .order_by(PreparedExerciseSet.created_at.asc())
            .first()
        )
        prepared_set = targeted_set or general_set

        exercises: List[ExercisePrompt] = []

        if prepared_set:
            if prepared_set.use_time_limit and prepared_set.time_limit_seconds:
                session_obj.time_limit_seconds = prepared_set.time_limit_seconds
                session_obj.time_limit_minutes = prepared_set.time_limit_seconds // 60
            session_obj.difficulty = "prepared"
            session_obj.session_type = "prepared"
            session_obj.instructions_fr = prepared_set.instructions_fr
            session_obj.instructions_en = prepared_set.instructions_en

            for index, question in enumerate(prepared_set.questions):
                db.session.add(
                    SessionExercise(
                        session_id=session_obj.id,
                        prompt=question.prompt,
                        correct_answer=question.answer,
                        category=question.category_code,
                        display_order=index,
                        source="prepared",
                    )
                )
            session_obj.total_questions = len(prepared_set.questions)
            prepared_set.mark_used()
        else:
            if use_skill_path:
                available_categories = QuestionCategory.query.filter(
                    QuestionCategory.code.in_(AVAILABLE_CATEGORIES)
                ).all()
                progress_map = _load_progress_map(student.id)
                prereq_map = _build_prerequisite_map()
                preferred_domains = _domain_list(student.preferred_domains)

                eligible_categories = [
                    category for category in available_categories
                    if _category_in_target(category, student)
                    and _is_category_unlocked(category, progress_map, prereq_map)
                ]
                if not eligible_categories:
                    eligible_categories = [
                        category for category in available_categories
                        if _category_in_target(category, student)
                    ]
                if not eligible_categories:
                    eligible_categories = available_categories

                weights = {
                    category.code: _category_priority(
                        category,
                        progress_map.get(category.id),
                        preferred_domains,
                    )
                    for category in eligible_categories
                }
                exercises = generate_exercises_for_categories(
                    [category.code for category in eligible_categories],
                    question_count,
                    difficulty=difficulty_value,
                    category_weights=weights,
                )
            else:
                exercises = generate_default_exercises(question_count, difficulty=difficulty_value)
            for index, exercise in enumerate(exercises):
                db.session.add(
                    SessionExercise(
                        session_id=session_obj.id,
                        display_order=index,
                        **_session_exercise_kwargs(exercise, source="procedural"),
                    )
                )
            session_obj.total_questions = len(exercises)

        db.session.commit()

        return redirect(url_for("sessions.play_session", session_id=session_obj.id))

    targeted_set = (
        PreparedExerciseSet.query.filter_by(is_used=False, student_id=student.id)
        .order_by(PreparedExerciseSet.created_at.asc())
        .first()
    )
    if targeted_set:
        session_obj = PracticeSession(
            student_id=student.id,
            time_limit_minutes=targeted_set.time_limit_seconds // 60
                if targeted_set.use_time_limit and targeted_set.time_limit_seconds else None,
            time_limit_seconds=targeted_set.time_limit_seconds
                if targeted_set.use_time_limit and targeted_set.time_limit_seconds else None,
            total_questions=len(targeted_set.questions),
            difficulty="prepared",
            session_type="prepared",
            instructions_fr=targeted_set.instructions_fr,
            instructions_en=targeted_set.instructions_en,
        )
        db.session.add(session_obj)
        db.session.flush()
        for index, question in enumerate(targeted_set.questions):
            db.session.add(
                SessionExercise(
                    session_id=session_obj.id,
                    prompt=question.prompt,
                    correct_answer=question.answer,
                    category=question.category_code,
                    display_order=index,
                    source="prepared",
                )
            )
        session_obj.total_questions = len(targeted_set.questions)
        targeted_set.mark_used()
        db.session.commit()
        flash(f"Session préparée lancée : {targeted_set.title}", "info")
        return redirect(url_for("sessions.play_session", session_id=session_obj.id))

    selected_difficulty = normalize_difficulty(request.args.get("difficulty"))
    default_mode = request.args.get("mode", "practice")
    return render_template(
        "session_form.html",
        student=student,
        difficulty_choices=consts["difficulty_choices"],
        selected_difficulty=selected_difficulty,
        difficulty_labels=consts["difficulty_labels"],
        default_adaptive=True,
        default_skill_path=True,
        recommended_difficulty=_recommend_difficulty(student),
        session_type_labels=consts["session_type_labels"],
        default_mode=default_mode,
    )
