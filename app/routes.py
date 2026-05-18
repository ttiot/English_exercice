from collections import Counter, defaultdict
import calendar
from datetime import date, datetime, timedelta
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
    flash,
    current_app,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from werkzeug.utils import secure_filename

try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from . import db, limiter
from .config import Config
from .exercise_factory import (
    ExercisePrompt,
    DIFFICULTY_LABELS,
    DIFFICULTY_LEVELS,
    generate_default_exercises,
    generate_exercises_for_categories,
    normalize_difficulty,
    AVAILABLE_CATEGORIES,
)
from .models import (
    AICallLog,
    AIGeneratedExercise,
    AppConfig,
    Badge,
    EmailConfig,
    OpenAIConfig,
    OpenAIPrompt,
    _safe_format,
    PracticeSession,
    PreparedExercise,
    PreparedExerciseQuestion,
    PreparedExerciseSet,
    ExerciseItem,
    QuestionCategory,
    ReviewPlan,
    SessionExercise,
    SessionTranslationLog,
    SkillPrerequisite,
    Student,
    StudentBadge,
    StudentSkillProgress,
    WeeklyGoal,
    WordTranslation,
)
from .services.auth import (
    _admin_required,
    _assert_student_access,
    _current_user,
    _get_student_or_404,
    _get_visible_students,
    _load_user_from_session,
    _login_required,
    _login_user,
    _logout_user,
    _parent_required,
    is_safe_url,
    require_login,
)
from .services.analytics import (
    _build_simple_pdf,
    _pdf_escape,
    _quarter_range,
    _student_recurring_errors,
    _student_theme_summary,
)
from .services.answer_validation import (
    _accepted_answers,
    _is_answer_correct,
    _normalize_answer,
    _prompt_has_blank,
    _session_exercise_kwargs,
    _strip_article,
)
from .services.curriculum import (
    DOMAIN_CHOICES,
    _category_in_target,
    _category_priority,
    _build_prerequisite_map,
    _cefr_rank,
    _difficulty_from_cefr,
    _domain_list,
    _filter_categories,
    _grade_rank,
    _is_category_unlocked,
    _load_progress_map,
    _parse_domain_list,
    _recommend_difficulty,
)
from .services.gamification import (
    DIFFICULTY_XP,
    LEVEL_TITLES,
    _award_badges,
    _compute_activity_heatmap,
    _compute_global_streak,
    _compute_weekly_progress,
    _compute_xp_and_level,
    _current_week_range,
    _get_weekly_goal,
    _review_interval_days,
    _select_instruction_language,
    _update_progress_from_session,
    _update_review_plan,
    _week_start,
)
from .services.imports import _parse_import_rows
from .validators import (
    validate_name,
    validate_email,
    validate_age,
    validate_goals,
    validate_password,
    sanitize_text_input,
    validate_question_content,
)

bp = Blueprint("main", __name__)

DIFFICULTY_DISPLAY = {**DIFFICULTY_LABELS, "prepared": "Parcours préparé"}
DIFFICULTY_CHOICES = [(value, DIFFICULTY_LABELS[value]) for value in DIFFICULTY_LEVELS]
CEFR_LEVELS = ["A1", "A2"]
GRADE_LEVELS = ["6e", "5e"]
TRIMESTER_CHOICES = [1, 2, 3]
SESSION_TYPE_LABELS = {
    "practice": "Entraînement",
    "challenge": "Défi",
    "control": "Contrôle",
    "prepared": "Parcours préparé",
    "ai_custom": "Prompt libre (IA)",
}

def _csv_safe(value) -> str:
    """Préfixe les cellules CSV commençant par un caractère de formule (=, +, -, @, |, %)
    pour prévenir l'injection de formules dans Excel / LibreOffice."""
    s = str(value) if value is not None else ""
    if s and s[0] in ('=', '+', '-', '@', '|', '%'):
        return "'" + s
    return s


def validate_image_file(file):
    """Validation stricte des fichiers image"""
    if not file or not file.filename:
        return False
    
    # Vérifier l'extension
    sanitized = secure_filename(file.filename)
    extension = sanitized.rsplit(".", 1)[-1].lower() if "." in sanitized else ""
    if extension not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
        return False
    
    # Vérifier le type MIME réel si python-magic est disponible
    if MAGIC_AVAILABLE:
        file_type = magic.from_buffer(file.read(1024), mime=True)
        file.seek(0)
        if file_type not in ['image/jpeg', 'image/png', 'image/gif']:
            return False
    
    # Vérifier que c'est vraiment une image si PIL est disponible
    if PIL_AVAILABLE:
        try:
            Image.open(file).verify()
            file.seek(0)
            return True
        except Exception:
            return False
    
    return True


bp.before_app_request(require_login)


def _slugify_label(label: str) -> str:
    slug = secure_filename(label.lower())
    return slug.replace("-", "_") or f"category_{uuid4().hex[:6]}"


def _delete_avatar_file(filename: Optional[str]) -> None:
    if not filename:
        return
    upload_folder = Path(current_app.config["UPLOAD_FOLDER"])
    candidate = upload_folder / filename
    if candidate.exists():
        try:
            candidate.unlink()
        except OSError:
            current_app.logger.warning("Impossible de supprimer l'ancien avatar %s", candidate)






def _update_progress_from_session(session_obj: PracticeSession) -> None:
    now = datetime.utcnow()
    category_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"correct": 0, "total": 0})
    for exercise in session_obj.exercises:
        category_stats[exercise.category]["total"] += 1
        if exercise.is_correct:
            category_stats[exercise.category]["correct"] += 1

    categories = QuestionCategory.query.filter(QuestionCategory.code.in_(category_stats.keys())).all()
    category_lookup = {category.code: category for category in categories}

    for category_code, stats in category_stats.items():
        category = category_lookup.get(category_code)
        if not category:
            continue
        progress = StudentSkillProgress.query.filter_by(
            student_id=session_obj.student_id,
            category_id=category.id,
        ).first()
        if not progress:
            progress = StudentSkillProgress(
                student_id=session_obj.student_id,
                category_id=category.id,
            )
            db.session.add(progress)
        if progress.total_attempts is None:
            progress.total_attempts = 0
        if progress.correct_attempts is None:
            progress.correct_attempts = 0
        if progress.correct_streak is None:
            progress.correct_streak = 0
        progress.total_attempts += stats["total"]
        progress.correct_attempts += stats["correct"]
        session_accuracy = (stats["correct"] / stats["total"]) * 100 if stats["total"] else 0.0
        progress.last_accuracy = session_accuracy
        progress.last_practiced = now
        if session_accuracy >= 80:
            progress.correct_streak += 1
        else:
            progress.correct_streak = 0
        progress.mastery = (
            (progress.correct_attempts / progress.total_attempts) * 100
            if progress.total_attempts
            else 0.0
        )


@bp.route("/students/new", methods=["GET", "POST"])
@_parent_required
def create_student():
    def _render_with_form_data(form_data: Dict[str, str], selected_domains: List[str]):
        return render_template(
            "student_form.html",
            form_data=form_data,
            selected_domains=selected_domains,
            cefr_levels=CEFR_LEVELS,
            grade_levels=GRADE_LEVELS,
            trimester_choices=TRIMESTER_CHOICES,
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

        # Validation stricte du prénom
        if not validate_name(first_name):
            flash("Le prénom contient des caractères invalides ou est trop long.", "danger")
            return _render_with_form_data(form_data, selected_domains)

        # Validation stricte du nom de famille
        if last_name and not validate_name(last_name):
            flash("Le nom de famille contient des caractères invalides ou est trop long.", "danger")
            return _render_with_form_data(form_data, selected_domains)

        # Validation stricte de l'email
        if not validate_email(email_raw):
            flash("L'adresse e-mail n'est pas valide.", "danger")
            return _render_with_form_data(form_data, selected_domains)

        if Student.query.filter_by(email=email_raw).first():
            flash("Cette adresse e-mail est déjà utilisée.", "danger")
            return _render_with_form_data(form_data, selected_domains)

        # Validation stricte du mot de passe
        password_valid, password_message = validate_password(password)
        if not password_valid:
            flash(password_message, "danger")
            return _render_with_form_data(form_data, selected_domains)

        if password != password_confirm:
            flash("La confirmation du mot de passe ne correspond pas.", "danger")
            return _render_with_form_data(form_data, selected_domains)

        # Validation stricte de l'âge
        age_value = validate_age(age_raw)
        if age_raw and age_value is None:
            flash("L'âge doit être un nombre valide entre 3 et 120 ans.", "danger")
            return _render_with_form_data(form_data, selected_domains)

        # Validation stricte des objectifs
        if goals and not validate_goals(goals):
            flash("Les objectifs contiennent du contenu invalide.", "danger")
            return _render_with_form_data(form_data, selected_domains)

        if target_cefr_level and target_cefr_level not in CEFR_LEVELS:
            flash("Le niveau CECRL est invalide.", "danger")
            return _render_with_form_data(form_data, selected_domains)

        if target_grade and target_grade not in GRADE_LEVELS:
            flash("Le niveau scolaire est invalide.", "danger")
            return _render_with_form_data(form_data, selected_domains)

        target_trimester = None
        if target_trimester_raw:
            try:
                target_trimester = int(target_trimester_raw)
            except ValueError:
                flash("Le trimestre est invalide.", "danger")
                return _render_with_form_data(form_data, selected_domains)
            if target_trimester not in TRIMESTER_CHOICES:
                flash("Le trimestre est invalide.", "danger")
                return _render_with_form_data(form_data, selected_domains)

        avatar_file = request.files.get("avatar")
        avatar_filename: Optional[str] = None
        if avatar_file and avatar_file.filename:
            if not validate_image_file(avatar_file):
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
        return redirect(url_for("main.view_student", student_id=student.id))

    return render_template(
        "student_form.html",
        form_data={},
        selected_domains=[],
        cefr_levels=CEFR_LEVELS,
        grade_levels=GRADE_LEVELS,
        trimester_choices=TRIMESTER_CHOICES,
        domain_choices=DOMAIN_CHOICES,
    )

@bp.route("/students/<int:student_id>")
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
        difficulty_labels=DIFFICULTY_DISPLAY,
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


@bp.route("/students/<int:student_id>/settings", methods=["GET", "POST"])
@_login_required
def manage_student(student_id: int):
    student = _get_student_or_404(student_id)

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
                return redirect(url_for("main.manage_student", student_id=student.id))

            if new_password != confirm_password:
                flash("La confirmation du mot de passe ne correspond pas.", "danger")
                return redirect(url_for("main.manage_student", student_id=student.id))

            if not parent_ok and not student.check_password(current_password):
                flash("L'ancien mot de passe est incorrect.", "danger")
                return redirect(url_for("main.manage_student", student_id=student.id))

            student.set_password(new_password)
            db.session.commit()
            flash("Mot de passe mis à jour avec succès.", "success")
            return redirect(url_for("main.manage_student", student_id=student.id))

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
            return redirect(url_for("main.manage_student", student_id=student.id))

        if not email_raw:
            flash("L'adresse e-mail est obligatoire.", "danger")
            return redirect(url_for("main.manage_student", student_id=student.id))

        existing_email = Student.query.filter_by(email=email_raw).first()
        if existing_email and existing_email.id != student.id:
            flash("Cette adresse e-mail est déjà utilisée.", "danger")
            return redirect(url_for("main.manage_student", student_id=student.id))

        try:
            age_value = int(age_raw) if age_raw else None
        except ValueError:
            flash("L'âge doit être un nombre.", "danger")
            return redirect(url_for("main.manage_student", student_id=student.id))

        if goals and not validate_goals(goals):
            flash("Les objectifs contiennent du contenu invalide.", "danger")
            return redirect(url_for("main.manage_student", student_id=student.id))

        if target_cefr_level and target_cefr_level not in CEFR_LEVELS:
            flash("Le niveau CECRL est invalide.", "danger")
            return redirect(url_for("main.manage_student", student_id=student.id))

        if target_grade and target_grade not in GRADE_LEVELS:
            flash("Le niveau scolaire est invalide.", "danger")
            return redirect(url_for("main.manage_student", student_id=student.id))

        target_trimester = None
        if target_trimester_raw:
            try:
                target_trimester = int(target_trimester_raw)
            except ValueError:
                flash("Le trimestre est invalide.", "danger")
                return redirect(url_for("main.manage_student", student_id=student.id))
            if target_trimester not in TRIMESTER_CHOICES:
                flash("Le trimestre est invalide.", "danger")
                return redirect(url_for("main.manage_student", student_id=student.id))

        avatar_file = request.files.get("avatar")
        new_avatar_filename: Optional[str] = None
        if avatar_file and avatar_file.filename:
            if not validate_image_file(avatar_file):
                flash("Format d'image non pris en charge ou fichier invalide.", "danger")
                return redirect(url_for("main.manage_student", student_id=student.id))

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
        return redirect(url_for("main.manage_student", student_id=student.id))

    return render_template(
        "student_settings.html",
        student=student,
        parent_ok=parent_ok,
        cefr_levels=CEFR_LEVELS,
        grade_levels=GRADE_LEVELS,
        trimester_choices=TRIMESTER_CHOICES,
        domain_choices=DOMAIN_CHOICES,
        selected_domains=_domain_list(student.preferred_domains),
    )


@bp.route("/students/<int:student_id>/sessions/new", methods=["GET", "POST"])
@_login_required
def start_session(student_id: int):
    student = _get_student_or_404(student_id)
    user = _current_user()
    if not (user.id == student.id or user.is_parent() or user.is_admin()):
        flash("Accès refusé.", "danger")
        return redirect(url_for("main.view_student", student_id=student.id))

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
            return redirect(url_for("main.start_session", student_id=student.id))

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
            from .services.ai_generator import (
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
                return redirect(url_for("main.start_session", student_id=student.id))
            if len(student_prompt) > 500:
                student_prompt = student_prompt[:500]

            client, _ = get_openai_client()
            if not client:
                flash(
                    "OpenAI n'est pas configuré. Demande à l'administrateur "
                    "d'activer le service IA.",
                    "danger",
                )
                return redirect(url_for("main.start_session", student_id=student.id))
            if is_budget_exceeded():
                flash(
                    "Le budget mensuel IA est atteint. Réessaie le mois prochain "
                    "ou demande à l'administrateur d'augmenter le plafond.",
                    "warning",
                )
                return redirect(url_for("main.start_session", student_id=student.id))

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
                return redirect(url_for("main.start_session", student_id=student.id))

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
            return redirect(url_for("main.play_session", session_id=session_obj.id))

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

        return redirect(url_for("main.play_session", session_id=session_obj.id))

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
        return redirect(url_for("main.play_session", session_id=session_obj.id))

    selected_difficulty = normalize_difficulty(request.args.get("difficulty"))
    default_mode = request.args.get("mode", "practice")
    return render_template(
        "session_form.html",
        student=student,
        difficulty_choices=DIFFICULTY_CHOICES,
        selected_difficulty=selected_difficulty,
        difficulty_labels=DIFFICULTY_DISPLAY,
        default_adaptive=True,
        default_skill_path=True,
        recommended_difficulty=_recommend_difficulty(student),
        session_type_labels=SESSION_TYPE_LABELS,
        default_mode=default_mode,
    )


@bp.route("/sessions/<int:session_id>", methods=["GET", "POST"])
@_login_required
def play_session(session_id: int):
    session_obj = PracticeSession.query.get_or_404(session_id)
    student = session_obj.student

    if not student:
        abort(404)

    user = _current_user()
    if not (user.id == student.id or user.is_parent() or user.is_admin()):
        flash("Accès refusé.", "danger")
        return redirect(url_for("main.view_student", student_id=student.id))

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
            from .email_service import send_session_completion_email
            send_session_completion_email(session_obj)
        except Exception:
            pass

        flash("Session terminée ! Voici ton score.", "success")
        return redirect(url_for("main.session_summary", session_id=session_obj.id))

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
    return render_template(
        "session_play.html",
        session_obj=session_obj,
        student=student,
        time_limit=time_limit,
        difficulty_labels=DIFFICULTY_DISPLAY,
        instructions=instructions,
        session_type_labels=SESSION_TYPE_LABELS,
        category_lookup=category_lookup,
    )


@bp.route("/sessions/<int:session_id>/autosave", methods=["POST"])
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


@bp.route("/sessions/<int:session_id>/summary")
@_login_required
def session_summary(session_id: int):
    session_obj = PracticeSession.query.get_or_404(session_id)
    student = session_obj.student
    if not student:
        abort(404)

    user = _current_user()
    if not (user.id == student.id or user.is_parent() or user.is_admin()):
        flash("Accès refusé.", "danger")
        return redirect(url_for("main.view_student", student_id=student.id))

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
    return render_template(
        "session_summary.html",
        session_obj=session_obj,
        category_lookup=category_lookup,
        difficulty_labels=DIFFICULTY_DISPLAY,
        session_type_labels=SESSION_TYPE_LABELS,
        last_reward=last_reward,
        translation_logs=translation_logs,
    )


@bp.route("/parents/dashboard")
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


@bp.route("/parents/students/<int:student_id>/weekly-goal", methods=["POST"])
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
        return redirect(url_for("main.parent_dashboard"))

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
    return redirect(url_for("main.parent_dashboard"))


@bp.route("/parents/students/<int:student_id>/report")
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


@bp.route("/parents/prepared-exercises/new", methods=["GET", "POST"])
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
            return redirect(url_for("main.create_prepared_exercise"))

        total_seconds = minutes_value * 60 + seconds_value
        if use_time_limit and total_seconds <= 0:
            flash("Indiquez un temps supérieur à zéro.", "danger")
            return redirect(url_for("main.create_prepared_exercise"))

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
                    return redirect(url_for("main.create_prepared_exercise"))
                
                questions_payload.append(
                    (prompt_clean, answer_clean, category_code)
                )

        if not questions_payload:
            flash("Ajoutez au moins une question valide.", "danger")
            return redirect(url_for("main.create_prepared_exercise"))

        student_obj: Optional[Student] = None
        if student_id and student_id != "all":
            try:
                student_obj = Student.query.get(int(student_id))
            except (TypeError, ValueError):
                student_obj = None
            if student_obj and student_obj.role != "student":
                student_obj = None

        exercise_set = PreparedExerciseSet(
            title=title,
            student=student_obj,
            use_time_limit=use_time_limit,
            time_limit_seconds=total_seconds if use_time_limit else None,
            instructions_fr=instructions_fr,
            instructions_en=instructions_en,
        )
        db.session.add(exercise_set)
        db.session.flush()

        for index, (prompt_clean, answer_clean, category_code) in enumerate(
            questions_payload
        ):
            db.session.add(
                PreparedExerciseQuestion(
                    exercise_set_id=exercise_set.id,
                    prompt=prompt_clean,
                    answer=answer_clean,
                    category_code=category_code,
                    position=index,
                )
            )

        db.session.commit()

        flash("Exercice préparé enregistré.", "success")
        return redirect(url_for("main.parent_dashboard"))

    return render_template(
        "prepared_exercise_form.html",
        students=students,
        categories=categories,
    )


@bp.route("/parents/import", methods=["GET", "POST"])
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
            return redirect(url_for("main.import_exercises"))

        content = file.read().decode("utf-8", errors="ignore")
        rows = _parse_import_rows(content, import_format, delimiter)
        if not rows:
            flash("Aucune question valide trouvée dans le fichier.", "warning")
            return redirect(url_for("main.import_exercises"))

        student_obj: Optional[Student] = None
        if student_id and student_id != "all":
            try:
                student_obj = Student.query.get(int(student_id))
            except (TypeError, ValueError):
                student_obj = None
            if student_obj and student_obj.role != "student":
                student_obj = None

        exercise_set = PreparedExerciseSet(
            title=title,
            student=student_obj,
            instructions_fr=instructions_fr,
            instructions_en=instructions_en,
        )
        db.session.add(exercise_set)
        db.session.flush()

        for index, row in enumerate(rows):
            prompt = sanitize_text_input(row["prompt"])
            answer = sanitize_text_input(row["answer"])
            category_code = row.get("category", "custom").strip() or "custom"
            if category_code not in category_codes:
                category_code = "custom"
            content_valid, content_message = validate_question_content(prompt, answer)
            if not content_valid:
                flash(f"Question ignorée : {content_message}", "warning")
                continue
            db.session.add(
                PreparedExerciseQuestion(
                    exercise_set_id=exercise_set.id,
                    prompt=prompt,
                    answer=answer,
                    category_code=category_code,
                    position=index,
                )
            )

        db.session.commit()
        flash("Import terminé : questions ajoutées.", "success")
        return redirect(url_for("main.parent_dashboard"))

    return render_template(
        "import_exercises.html",
        students=students,
        categories=categories,
    )


@bp.route("/exercise-bank")
@_login_required
def exercise_bank():
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
        cefr_levels=CEFR_LEVELS,
        grade_levels=GRADE_LEVELS,
        trimester_choices=TRIMESTER_CHOICES,
        selected_domain=domain,
        selected_cefr=cefr,
        selected_grade=grade,
        selected_trimester=trimester,
        prereq_map=prereq_map,
        exercise_items=exercise_items,
    )


@bp.route("/exercise-bank/generate", methods=["POST"])
@_login_required
def generate_exercises_from_bank():
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
        cefr_levels=CEFR_LEVELS,
        grade_levels=GRADE_LEVELS,
        trimester_choices=TRIMESTER_CHOICES,
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


@bp.route("/exercise-bank/items", methods=["POST"])
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
        return redirect(url_for("main.exercise_bank"))

    if not prompt or not answer:
        flash("La question et la réponse sont obligatoires.", "danger")
        return redirect(url_for("main.exercise_bank"))

    content_valid, content_message = validate_question_content(prompt, answer)
    if not content_valid:
        flash(f"Question invalide : {content_message}", "danger")
        return redirect(url_for("main.exercise_bank"))

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
    return redirect(url_for("main.exercise_bank"))


@bp.route("/exercise-bank/ai")
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


@bp.route("/exercise-bank/ai/<int:item_id>/toggle", methods=["POST"])
@_parent_required
def toggle_ai_exercise(item_id: int):
    item = AIGeneratedExercise.query.get_or_404(item_id)
    item.is_disabled = not item.is_disabled
    db.session.commit()
    flash(
        "Exercice IA désactivé." if item.is_disabled else "Exercice IA réactivé.",
        "info",
    )
    return redirect(url_for("main.ai_exercise_pool"))


@bp.route("/exercise-bank/items/<int:item_id>/delete", methods=["POST"])
@_parent_required
def delete_exercise_item(item_id: int):
    item = ExerciseItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    flash("Question supprimée.", "success")
    return redirect(url_for("main.exercise_bank"))


@bp.route("/parents/categories/new", methods=["POST"])
@_parent_required
def create_category():

    label = request.form.get("name", "").strip()
    if not label:
        flash("Le nom de la catégorie est requis.", "danger")
        return redirect(url_for("main.parent_dashboard"))

    code = _slugify_label(label)
    existing = QuestionCategory.query.filter(
        (QuestionCategory.code == code) | (QuestionCategory.name == label)
    ).first()
    if existing:
        flash("Cette catégorie existe déjà.", "warning")
        return redirect(url_for("main.parent_dashboard"))

    db.session.add(QuestionCategory(code=code, name=label))
    db.session.commit()
    flash("Catégorie créée.", "success")
    return redirect(url_for("main.parent_dashboard"))


@bp.route("/parents/categories/<int:category_id>/rename", methods=["POST"])
@_parent_required
def rename_category(category_id: int):

    category = QuestionCategory.query.get_or_404(category_id)
    new_label = request.form.get("name", "").strip()
    if not new_label:
        flash("Le nom ne peut pas être vide.", "danger")
        return redirect(url_for("main.parent_dashboard"))

    new_code = _slugify_label(new_label)
    conflict = QuestionCategory.query.filter(
        (QuestionCategory.id != category.id)
        & ((QuestionCategory.code == new_code) | (QuestionCategory.name == new_label))
    ).first()
    if conflict:
        flash("Une autre catégorie porte déjà ce nom.", "warning")
        return redirect(url_for("main.parent_dashboard"))

    old_code = category.code
    category.name = new_label
    category.code = new_code

    SessionExercise.query.filter_by(category=old_code).update({"category": new_code})
    PreparedExerciseQuestion.query.filter_by(category_code=old_code).update(
        {"category_code": new_code}
    )

    db.session.commit()
    flash("Catégorie mise à jour.", "success")
    return redirect(url_for("main.parent_dashboard"))


@bp.route("/parents/categories/<int:category_id>/delete", methods=["POST"])
@_parent_required
def delete_category(category_id: int):

    category = QuestionCategory.query.get_or_404(category_id)

    in_use = SessionExercise.query.filter_by(category=category.code).first() or PreparedExerciseQuestion.query.filter_by(
        category_code=category.code
    ).first()
    if in_use:
        flash("Impossible de supprimer une catégorie utilisée.", "warning")
        return redirect(url_for("main.parent_dashboard"))

    db.session.delete(category)
    db.session.commit()
    flash("Catégorie supprimée.", "success")
    return redirect(url_for("main.parent_dashboard"))


@bp.route("/parents/sessions/<int:session_id>/delete", methods=["POST"])
@_parent_required
def delete_session(session_id: int):
    session_obj = PracticeSession.query.get(session_id)
    if not session_obj:
        flash("Session introuvable ou déjà supprimée.", "warning")
        return redirect(url_for("main.parent_dashboard"))

    _assert_student_access(_current_user(), session_obj.student)
    student_id = session_obj.student_id

    db.session.delete(session_obj)
    db.session.commit()

    flash("La session a été supprimée.", "success")
    return redirect(url_for("main.view_student", student_id=student_id))


@bp.route(
    "/parents/sessions/<int:session_id>/exercises/<int:exercise_id>/toggle-correct",
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
    return redirect(url_for("main.session_summary", session_id=session_id))


@bp.route(
    "/parents/sessions/<int:session_id>/exercises/<int:exercise_id>/edit",
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
        return redirect(url_for("main.session_summary", session_id=session_id))

    return render_template(
        "edit_exercise.html",
        session_obj=session_obj,
        exercise=exercise,
        categories=categories,
        form_data=None,
    )


@bp.route(
    "/parents/students/<int:student_id>/generate-ai-exercises",
    methods=["GET", "POST"],
)
@_parent_required
def parent_generate_ai_exercises(student_id: int):
    student = _get_student_or_404(student_id)
    _assert_student_access(_current_user(), student)

    if request.method == "POST":
        from .services.ai_generator import generate_exercises as ai_generate_exercises, get_openai_client, is_budget_exceeded

        student_prompt = sanitize_text_input(request.form.get("student_prompt", ""))
        difficulty = request.form.get("difficulty", "beginner").strip()
        try:
            question_count = int(request.form.get("question_count", 10))
            question_count = max(5, min(25, question_count))
        except (ValueError, TypeError):
            question_count = 10

        if len(student_prompt) < 5:
            flash("Le sujet doit contenir au moins 5 caractères.", "danger")
            return render_template(
                "parent_ai_generate.html",
                student=student,
                difficulty_labels=DIFFICULTY_DISPLAY,
                form_data={"student_prompt": student_prompt, "difficulty": difficulty, "question_count": question_count},
            )

        if difficulty not in DIFFICULTY_LEVELS:
            difficulty = "beginner"

        client, client_info = get_openai_client()
        if client is None:
            flash("La génération IA n'est pas disponible (aucune clé API configurée).", "warning")
            return redirect(url_for("main.view_student", student_id=student_id))

        if is_budget_exceeded():
            flash("Le budget mensuel de génération IA est atteint.", "warning")
            return redirect(url_for("main.view_student", student_id=student_id))

        results = ai_generate_exercises(student_prompt, question_count, difficulty, student_id)

        if not results:
            flash("La génération n'a produit aucun exercice. Reformule le sujet et réessaie.", "danger")
            return render_template(
                "parent_ai_generate.html",
                student=student,
                difficulty_labels=DIFFICULTY_DISPLAY,
                form_data={"student_prompt": student_prompt, "difficulty": difficulty, "question_count": question_count},
            )

        safe_prompt = student_prompt[:50]
        exercise_set = PreparedExerciseSet(
            title=f"IA : {safe_prompt}",
            student_id=student.id,
        )
        db.session.add(exercise_set)
        db.session.flush()

        for idx, (ep, _pool_row) in enumerate(results):
            q = PreparedExerciseQuestion(
                exercise_set_id=exercise_set.id,
                prompt=ep.prompt,
                answer=ep.answer,
                category_code=ep.category,
                position=idx,
            )
            db.session.add(q)

        db.session.commit()

        flash(
            f"{len(results)} exercice(s) générés et assignés à {student.full_name()}. "
            "Ils seront proposés lors de sa prochaine session.",
            "success",
        )
        return redirect(url_for("main.view_student", student_id=student_id))

    return render_template(
        "parent_ai_generate.html",
        student=student,
        difficulty_labels=DIFFICULTY_DISPLAY,
        form_data=None,
    )


@bp.route("/admin/users")
@_admin_required
def admin_users():
    """Gestion des comptes utilisateurs."""
    all_users = Student.query.order_by(Student.first_name, Student.last_name).all()
    return render_template("admin/users.html", all_users=all_users)


@bp.route("/admin/users/<int:user_id>/role", methods=["POST"])
@_admin_required
def update_user_role(user_id: int):
    target = _get_student_or_404(user_id)
    new_role = request.form.get("role", "student").strip()

    if new_role not in {"student", "parent", "admin"}:
        flash("Type de compte invalide.", "danger")
        return redirect(url_for("main.parent_dashboard"))

    current_user = _current_user()
    if current_user.id == target.id and new_role != "admin":
        flash("Tu ne peux pas retirer ton propre rôle d'administrateur.", "warning")
        return redirect(url_for("main.admin_users"))

    target.role = new_role
    db.session.commit()
    flash("Rôle utilisateur mis à jour.", "success")
    return redirect(url_for("main.admin_users"))


@bp.route("/admin/users/<int:user_id>/impersonate", methods=["POST"])
@_admin_required
def impersonate_user(user_id: int):
    if session.get("original_admin_id"):
        flash("Terminez d'abord la session d'impersonnification en cours.", "warning")
        return redirect(url_for("main.admin_users"))
    target = _get_student_or_404(user_id)
    session["original_admin_id"] = session["user_id"]
    session["user_id"] = target.id
    g.pop("current_user", None)
    flash(f"Vous impersonnifiez {target.full_name()}.", "info")
    return redirect(url_for("auth.index"))


@bp.route("/admin/stop-impersonation", methods=["POST"])
def stop_impersonation():
    original_id = session.pop("original_admin_id", None)
    if not original_id:
        return redirect(url_for("auth.index"))
    session["user_id"] = original_id
    g.pop("current_user", None)
    flash("Impersonnification terminée.", "success")
    return redirect(url_for("main.admin_users"))


@bp.route("/admin/users/<int:parent_id>/students", methods=["GET", "POST"])
@_admin_required
def admin_parent_students(parent_id: int):
    parent = _get_student_or_404(parent_id)
    if not parent.is_parent():
        flash("Cet utilisateur n'est pas un parent.", "warning")
        return redirect(url_for("main.admin_users"))

    all_students = Student.query.filter_by(role="student").order_by(Student.first_name).all()

    if request.method == "POST":
        selected_ids = set()
        for raw in request.form.getlist("student_ids"):
            try:
                selected_ids.add(int(raw))
            except (ValueError, TypeError):
                pass
        parent.managed_students = [s for s in all_students if s.id in selected_ids]
        db.session.commit()
        flash("Rattachements mis à jour.", "success")
        return redirect(url_for("main.admin_users"))

    return render_template(
        "admin/parent_students.html",
        parent=parent,
        all_students=all_students,
    )


@bp.route("/admin/users/new", methods=["GET", "POST"])
@_admin_required
def admin_create_user():
    def _render(form_data, selected_domains):
        return render_template(
            "admin/user_form.html",
            user=None,
            form_data=form_data,
            selected_domains=selected_domains,
            cefr_levels=CEFR_LEVELS,
            grade_levels=GRADE_LEVELS,
            trimester_choices=TRIMESTER_CHOICES,
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
        role = request.form.get("role", "student").strip()
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
            "role": role,
        }
        selected_domains = request.form.getlist("preferred_domains")

        if role not in {"student", "parent", "admin"}:
            flash("Rôle invalide.", "danger")
            return _render(form_data, selected_domains)

        if role != "student":
            age_raw = ""
            goals = None
            target_cefr_level = None
            target_grade = None
            target_trimester_raw = ""
            interests = None
            preferred_domains = None

        if not validate_name(first_name):
            flash("Le prénom contient des caractères invalides ou est trop long.", "danger")
            return _render(form_data, selected_domains)

        if last_name and not validate_name(last_name):
            flash("Le nom de famille contient des caractères invalides ou est trop long.", "danger")
            return _render(form_data, selected_domains)

        if not validate_email(email_raw):
            flash("L'adresse e-mail n'est pas valide.", "danger")
            return _render(form_data, selected_domains)

        if Student.query.filter_by(email=email_raw).first():
            flash("Cette adresse e-mail est déjà utilisée.", "danger")
            return _render(form_data, selected_domains)

        password_valid, password_message = validate_password(password)
        if not password_valid:
            flash(password_message, "danger")
            return _render(form_data, selected_domains)

        if password != password_confirm:
            flash("La confirmation du mot de passe ne correspond pas.", "danger")
            return _render(form_data, selected_domains)

        age_value = validate_age(age_raw)
        if age_raw and age_value is None:
            flash("L'âge doit être un nombre valide entre 3 et 120 ans.", "danger")
            return _render(form_data, selected_domains)

        if goals and not validate_goals(goals):
            flash("Les objectifs contiennent du contenu invalide.", "danger")
            return _render(form_data, selected_domains)

        if target_cefr_level and target_cefr_level not in CEFR_LEVELS:
            flash("Le niveau CECRL est invalide.", "danger")
            return _render(form_data, selected_domains)

        if target_grade and target_grade not in GRADE_LEVELS:
            flash("Le niveau scolaire est invalide.", "danger")
            return _render(form_data, selected_domains)

        target_trimester = None
        if target_trimester_raw:
            try:
                target_trimester = int(target_trimester_raw)
            except ValueError:
                flash("Le trimestre est invalide.", "danger")
                return _render(form_data, selected_domains)
            if target_trimester not in TRIMESTER_CHOICES:
                flash("Le trimestre est invalide.", "danger")
                return _render(form_data, selected_domains)

        avatar_file = request.files.get("avatar")
        avatar_filename: Optional[str] = None
        if avatar_file and avatar_file.filename:
            if not validate_image_file(avatar_file):
                flash("Format d'image non pris en charge ou fichier invalide.", "danger")
                return _render(form_data, selected_domains)
            sanitized = secure_filename(avatar_file.filename)
            extension = sanitized.rsplit(".", 1)[-1].lower() if "." in sanitized else ""
            avatar_filename = f"{uuid4().hex}.{extension}"
            avatar_file.save(Path(current_app.config["UPLOAD_FOLDER"]) / avatar_filename)

        new_user = Student(
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
            role=role,
        )
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash(f"Compte « {new_user.full_name()} » créé.", "success")
        return redirect(url_for("main.admin_users"))

    return _render({}, [])


@bp.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
@_admin_required
def admin_edit_user(user_id: int):
    target = _get_student_or_404(user_id)

    def _render(form_data, selected_domains):
        return render_template(
            "admin/user_form.html",
            user=target,
            form_data=form_data,
            selected_domains=selected_domains,
            cefr_levels=CEFR_LEVELS,
            grade_levels=GRADE_LEVELS,
            trimester_choices=TRIMESTER_CHOICES,
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
        role = request.form.get("role", target.role).strip()
        password = request.form.get("password", "").strip()
        password_confirm = request.form.get("password_confirm", "").strip()
        remove_avatar = request.form.get("remove_avatar") == "on"
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
            "role": role,
        }
        selected_domains = request.form.getlist("preferred_domains")

        if role not in {"student", "parent", "admin"}:
            flash("Rôle invalide.", "danger")
            return _render(form_data, selected_domains)

        if role != "student":
            age_raw = ""
            goals = None
            target_cefr_level = None
            target_grade = None
            target_trimester_raw = ""
            interests = None
            preferred_domains = None

        current_user_obj = _current_user()
        if current_user_obj.id == target.id and role != "admin":
            flash("Vous ne pouvez pas retirer votre propre rôle d'administrateur.", "warning")
            return _render(form_data, selected_domains)

        if not validate_name(first_name):
            flash("Le prénom contient des caractères invalides ou est trop long.", "danger")
            return _render(form_data, selected_domains)

        if last_name and not validate_name(last_name):
            flash("Le nom de famille contient des caractères invalides ou est trop long.", "danger")
            return _render(form_data, selected_domains)

        if not validate_email(email_raw):
            flash("L'adresse e-mail n'est pas valide.", "danger")
            return _render(form_data, selected_domains)

        conflict = Student.query.filter(
            Student.email == email_raw, Student.id != target.id
        ).first()
        if conflict:
            flash("Cette adresse e-mail est déjà utilisée.", "danger")
            return _render(form_data, selected_domains)

        if password:
            password_valid, password_message = validate_password(password)
            if not password_valid:
                flash(password_message, "danger")
                return _render(form_data, selected_domains)
            if password != password_confirm:
                flash("La confirmation du mot de passe ne correspond pas.", "danger")
                return _render(form_data, selected_domains)

        age_value = validate_age(age_raw)
        if age_raw and age_value is None:
            flash("L'âge doit être un nombre valide entre 3 et 120 ans.", "danger")
            return _render(form_data, selected_domains)

        if goals and not validate_goals(goals):
            flash("Les objectifs contiennent du contenu invalide.", "danger")
            return _render(form_data, selected_domains)

        if target_cefr_level and target_cefr_level not in CEFR_LEVELS:
            flash("Le niveau CECRL est invalide.", "danger")
            return _render(form_data, selected_domains)

        if target_grade and target_grade not in GRADE_LEVELS:
            flash("Le niveau scolaire est invalide.", "danger")
            return _render(form_data, selected_domains)

        target_trimester = None
        if target_trimester_raw:
            try:
                target_trimester = int(target_trimester_raw)
            except ValueError:
                flash("Le trimestre est invalide.", "danger")
                return _render(form_data, selected_domains)
            if target_trimester not in TRIMESTER_CHOICES:
                flash("Le trimestre est invalide.", "danger")
                return _render(form_data, selected_domains)

        avatar_file = request.files.get("avatar")
        new_avatar_filename: Optional[str] = None
        if avatar_file and avatar_file.filename:
            if not validate_image_file(avatar_file):
                flash("Format d'image non pris en charge ou fichier invalide.", "danger")
                return _render(form_data, selected_domains)
            sanitized = secure_filename(avatar_file.filename)
            extension = sanitized.rsplit(".", 1)[-1].lower() if "." in sanitized else ""
            new_avatar_filename = f"{uuid4().hex}.{extension}"
            avatar_file.save(Path(current_app.config["UPLOAD_FOLDER"]) / new_avatar_filename)

        if remove_avatar and target.avatar_filename:
            _delete_avatar_file(target.avatar_filename)
            target.avatar_filename = None

        if new_avatar_filename:
            if target.avatar_filename:
                _delete_avatar_file(target.avatar_filename)
            target.avatar_filename = new_avatar_filename

        target.first_name = first_name
        target.last_name = last_name
        target.email = email_raw
        target.age = age_value
        target.goals = goals
        target.target_cefr_level = target_cefr_level
        target.target_grade = target_grade
        target.target_trimester = target_trimester
        target.interests = interests
        target.preferred_domains = preferred_domains or None
        target.role = role
        if password:
            target.set_password(password)
        db.session.commit()
        flash("Compte mis à jour.", "success")
        return redirect(url_for("main.admin_users"))

    form_data = {
        "first_name": target.first_name,
        "last_name": target.last_name or "",
        "email": target.email or "",
        "age": str(target.age) if target.age else "",
        "goals": target.goals or "",
        "target_cefr_level": target.target_cefr_level or "",
        "target_grade": target.target_grade or "",
        "target_trimester": str(target.target_trimester) if target.target_trimester else "",
        "interests": target.interests or "",
        "role": target.role,
    }
    selected_domains = _domain_list(target.preferred_domains)
    return _render(form_data, selected_domains)


@bp.route("/admin/users/<int:user_id>/delete", methods=["GET", "POST"])
@_admin_required
def admin_delete_user(user_id: int):
    target = _get_student_or_404(user_id)

    if target.id == _current_user().id:
        flash("Vous ne pouvez pas supprimer votre propre compte.", "warning")
        return redirect(url_for("main.admin_users"))

    if request.method == "POST":
        name = target.full_name()

        target.managed_students.clear()
        for sess in list(target.sessions):
            db.session.delete(sess)

        WeeklyGoal.query.filter_by(student_id=target.id).delete()
        StudentBadge.query.filter_by(student_id=target.id).delete()
        ReviewPlan.query.filter_by(student_id=target.id).delete()
        StudentSkillProgress.query.filter_by(student_id=target.id).delete()
        PreparedExercise.query.filter_by(student_id=target.id).update({"student_id": None})
        PreparedExerciseSet.query.filter_by(student_id=target.id).update({"student_id": None})
        AICallLog.query.filter_by(student_id=target.id).update({"student_id": None})

        _delete_avatar_file(target.avatar_filename)
        db.session.delete(target)
        db.session.commit()
        flash(f"Compte « {name} » supprimé.", "success")
        return redirect(url_for("main.admin_users"))

    session_count = len(target.sessions)
    badge_count = len(target.badges)
    return render_template(
        "admin/user_delete.html",
        target=target,
        session_count=session_count,
        badge_count=badge_count,
    )


# --- Admin OpenAI ----------------------------------------------------------

OPENAI_MODEL_CHOICES = (
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo",
    "gpt-5-mini",
    "gpt-5",
    "o1-mini",
    "o1",
)


@bp.route("/admin/openai/config", methods=["GET", "POST"])
@_admin_required
def admin_openai_config():
    config = OpenAIConfig.get_or_create()
    test_result = None

    if request.method == "POST":
        action = request.form.get("action", "save")

        if action == "test":
            from .services.ai_generator import test_connection

            test_result = test_connection()
            if test_result.get("success"):
                flash(
                    "Connexion OpenAI OK. Modèle par défaut : "
                    f"{test_result.get('default_model')}",
                    "success",
                )
            else:
                flash(
                    f"Échec du test : {test_result.get('error', 'erreur inconnue')}",
                    "danger",
                )
        elif action == "clear":
            config.set_api_key(None)
            db.session.commit()
            flash("Clé API supprimée.", "info")
            return redirect(url_for("main.admin_openai_config"))
        else:  # save
            api_key = request.form.get("api_key", "").strip()
            base_url = request.form.get("base_url", "").strip() or None
            default_model = request.form.get("default_model", "").strip() or None
            source_name = request.form.get("source_name", "").strip() or None
            monthly_budget = request.form.get("monthly_budget", "").strip()
            is_active = bool(request.form.get("is_active"))

            if api_key:
                config.set_api_key(api_key)
            config.base_url = base_url or "https://api.openai.com/v1"
            config.default_model = default_model or "gpt-4o-mini"
            config.source_name = source_name or "OpenAI"
            config.is_active = is_active
            if monthly_budget:
                try:
                    config.monthly_budget_usd = float(monthly_budget)
                except ValueError:
                    flash("Budget mensuel invalide.", "warning")
                    config.monthly_budget_usd = None
            else:
                config.monthly_budget_usd = None

            db.session.commit()
            flash("Configuration OpenAI enregistrée.", "success")
            return redirect(url_for("main.admin_openai_config"))

    return render_template(
        "admin/openai_config.html",
        config=config,
        model_choices=OPENAI_MODEL_CHOICES,
        test_result=test_result,
    )


@bp.route("/admin/openai/logs")
@_admin_required
def admin_openai_logs():
    from sqlalchemy import desc

    page = max(int(request.args.get("page", 1) or 1), 1)
    per_page = 25
    status = request.args.get("status", "").strip()
    call_type = request.args.get("call_type", "").strip()

    query = AICallLog.query
    if status:
        query = query.filter(AICallLog.response_status == status)
    if call_type:
        query = query.filter(AICallLog.call_type == call_type)
    query = query.order_by(desc(AICallLog.created_at))

    total = query.count()
    logs = query.offset((page - 1) * per_page).limit(per_page).all()
    student_lookup = {
        student.id: student
        for student in Student.query.filter(
            Student.id.in_({log.student_id for log in logs if log.student_id})
        ).all()
    }

    return render_template(
        "admin/openai_logs.html",
        logs=logs,
        student_lookup=student_lookup,
        page=page,
        per_page=per_page,
        total=total,
        status=status,
        call_type=call_type,
    )


@bp.route("/admin/openai/logs/<int:log_id>")
@_admin_required
def admin_openai_log_detail(log_id: int):
    log = AICallLog.query.get_or_404(log_id)
    student = Student.query.get(log.student_id) if log.student_id else None
    return render_template(
        "admin/openai_log_detail.html",
        log=log,
        student=student,
    )


@bp.route("/admin/openai/budget")
@_admin_required
def admin_openai_budget():
    config = OpenAIConfig.get_active()
    today = datetime.utcnow()
    months: List[dict] = []
    for offset in range(0, 3):
        # 3 derniers mois (incluant le courant).
        year = today.year
        month = today.month - offset
        while month <= 0:
            month += 12
            year -= 1
        months.append(AICallLog.get_monthly_stats(year=year, month=month))

    current = months[0]
    budget = float(config.monthly_budget_usd) if config and config.monthly_budget_usd else None
    spent = float(current.get("cost_usd") or 0.0)
    ratio = (spent / budget * 100) if budget else None

    return render_template(
        "admin/openai_budget.html",
        config=config,
        months=months,
        budget=budget,
        spent=spent,
        ratio=ratio,
    )


@bp.route("/admin/openai/")
@_admin_required
def admin_openai_hub():
    """Page d'accueil du panneau d'administration OpenAI."""
    config = OpenAIConfig.get_active()
    current = AICallLog.get_monthly_stats()
    success_stats = AICallLog.get_success_stats()
    avg_latency = AICallLog.get_avg_latency_ms()
    has_key = bool(config and config.get_api_key())
    budget = float(config.monthly_budget_usd) if config and config.monthly_budget_usd else None
    spent = float(current.get("cost_usd") or 0.0)
    budget_ratio = (spent / budget * 100) if budget else None

    return render_template(
        "admin/openai_hub.html",
        config=config,
        has_key=has_key,
        current=current,
        success_stats=success_stats,
        avg_latency=avg_latency,
        budget=budget,
        spent=spent,
        budget_ratio=budget_ratio,
    )


@bp.route("/admin/openai/prompts")
@_admin_required
def admin_openai_prompts():
    """Liste des prompts éditables."""
    from .services.ai_generator import _DEFAULT_PROMPTS

    # On garantit que toutes les clés connues existent en BDD (pour l'affichage).
    for key in _DEFAULT_PROMPTS:
        OpenAIPrompt.get_or_create_default(key)

    prompts = OpenAIPrompt.query.order_by(OpenAIPrompt.prompt_key.asc()).all()
    return render_template(
        "admin/openai_prompts.html",
        prompts=prompts,
        default_keys=set(_DEFAULT_PROMPTS.keys()),
    )


@bp.route("/admin/openai/prompts/<prompt_key>", methods=["GET", "POST"])
@_admin_required
def admin_openai_prompt_edit(prompt_key: str):
    """Édition du prompt système / utilisateur / paramètres."""
    prompt = OpenAIPrompt.get_or_create_default(prompt_key)
    if not prompt:
        abort(404)

    if request.method == "POST":
        display_name = sanitize_text_input(request.form.get("display_name", ""))
        description = sanitize_text_input(request.form.get("description", ""))
        # Pas de sanitize sur les prompts : on veut préserver le formatage
        # (sauts de ligne, accolades de templating, etc.). On limite juste
        # la longueur pour éviter une surcharge.
        system_prompt = (request.form.get("system_prompt") or "")[:20000]
        user_prompt_template = (request.form.get("user_prompt_template") or "")[:20000]
        max_tokens_raw = request.form.get("max_output_tokens", "").strip()
        is_active = bool(request.form.get("is_active"))

        def _validate_template(tmpl: str) -> bool:
            try:
                _safe_format(tmpl)
            except ValueError:
                return False
            except (KeyError, IndexError):
                pass
            return True

        if not display_name:
            flash("Le nom d'affichage est requis.", "warning")
        elif not system_prompt or not user_prompt_template:
            flash("Le prompt système et le prompt utilisateur sont requis.", "warning")
        elif not _validate_template(system_prompt) or not _validate_template(user_prompt_template):
            flash("Le template contient des placeholders non autorisés (accès attribut/index interdit).", "danger")
        else:
            prompt.display_name = display_name
            prompt.description = description or None
            prompt.system_prompt = system_prompt
            prompt.user_prompt_template = user_prompt_template
            prompt.is_active = is_active

            params = prompt.get_parameters()
            if max_tokens_raw:
                try:
                    params["max_output_tokens"] = max(64, min(int(max_tokens_raw), 16000))
                except ValueError:
                    flash("Nombre de tokens max invalide, ignoré.", "warning")
            prompt.parameters_json = json.dumps(params) if params else None

            db.session.commit()
            flash("Prompt enregistré.", "success")
            return redirect(url_for("main.admin_openai_prompt_edit", prompt_key=prompt_key))

    from .services.ai_generator import _DEFAULT_PROMPTS

    return render_template(
        "admin/openai_prompt_edit.html",
        prompt=prompt,
        is_default_known=prompt_key in _DEFAULT_PROMPTS,
        max_output_tokens=int(prompt.get_parameters().get("max_output_tokens") or 2000),
        available_variables=prompt.get_available_variables(),
    )


@bp.route("/admin/openai/prompts/<prompt_key>/reset", methods=["POST"])
@_admin_required
def admin_openai_prompt_reset(prompt_key: str):
    """Restaure les valeurs par défaut hardcodées pour ce prompt."""
    prompt = OpenAIPrompt.query.filter_by(prompt_key=prompt_key).first()
    if not prompt:
        abort(404)
    if prompt.reset_to_default():
        db.session.commit()
        flash("Prompt réinitialisé aux valeurs par défaut.", "success")
    else:
        flash("Aucune valeur par défaut connue pour cette clé.", "warning")
    return redirect(url_for("main.admin_openai_prompt_edit", prompt_key=prompt_key))


@bp.route("/admin/openai/statistics")
@_admin_required
def admin_openai_statistics():
    """Tableau de bord d'usage OpenAI : trend annuel, top élèves, taux de succès."""
    config = OpenAIConfig.get_active()
    current = AICallLog.get_monthly_stats()
    success_stats = AICallLog.get_success_stats()
    avg_latency = AICallLog.get_avg_latency_ms()
    trend = AICallLog.get_yearly_trend(months=12)
    top_students = AICallLog.get_top_students(limit=10)

    budget = float(config.monthly_budget_usd) if config and config.monthly_budget_usd else None
    spent = float(current.get("cost_usd") or 0.0)
    budget_ratio = (spent / budget * 100) if budget else None

    return render_template(
        "admin/openai_statistics.html",
        config=config,
        current=current,
        success_stats=success_stats,
        avg_latency=avg_latency,
        trend=trend,
        trend_labels=[bucket["label"] for bucket in trend],
        trend_calls=[bucket["calls"] for bucket in trend],
        trend_costs=[round(bucket["cost_usd"], 4) for bucket in trend],
        top_students=top_students,
        budget=budget,
        spent=spent,
        budget_ratio=budget_ratio,
    )


# ---------------------------------------------------------------------------
# Administration système
# ---------------------------------------------------------------------------

@bp.route("/admin/system", methods=["GET", "POST"])
@_admin_required
def admin_system_config():
    """Configuration système : clé de chiffrement des sauvegardes, etc."""
    app_config = AppConfig.get_or_create()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "save_backup_key":
            raw_key = request.form.get("backup_key", "").strip()
            if raw_key:
                app_config.set_backup_key(raw_key)
                db.session.commit()
                if app_config.export_key_file():
                    flash("Clé de chiffrement backup enregistrée et exportée.", "success")
                else:
                    flash("Clé enregistrée en base, mais l'export vers /data/.backup_key a échoué.", "warning")
            else:
                flash("La clé ne peut pas être vide.", "warning")

        elif action == "clear_backup_key":
            app_config.set_backup_key(None)
            db.session.commit()
            app_config.export_key_file()
            flash("Clé de chiffrement backup supprimée.", "info")

        elif action == "generate_backup_key":
            from cryptography.fernet import Fernet
            new_key = Fernet.generate_key().decode()
            app_config.set_backup_key(new_key)
            db.session.commit()
            if app_config.export_key_file():
                flash(f"Nouvelle clé générée et exportée. Copiez-la maintenant : {new_key}", "success")
            else:
                flash(f"Nouvelle clé générée : {new_key}. Export vers /data/.backup_key a échoué.", "warning")

        return redirect(url_for("main.admin_system_config"))

    has_backup_key = bool(app_config.backup_key_encrypted)
    return render_template(
        "admin/app_config.html",
        app_config=app_config,
        has_backup_key=has_backup_key,
    )


@bp.route("/admin/email/config", methods=["GET", "POST"])
@_admin_required
def admin_email_config():
    """Configuration du serveur SMTP pour l'envoi d'emails."""
    from .email_service import send_email, test_smtp_connection

    config = EmailConfig.get_or_create()
    test_result = None

    if request.method == "POST":
        action = request.form.get("action", "save")

        if action == "save":
            config.host = sanitize_text_input(request.form.get("host", "")).strip()
            try:
                config.port = int(request.form.get("port") or 587)
            except ValueError:
                config.port = 587
            config.use_tls = request.form.get("use_tls") == "on"
            config.use_ssl = request.form.get("use_ssl") == "on"
            config.username = sanitize_text_input(request.form.get("username", "")).strip()
            pwd = request.form.get("password", "").strip()
            if pwd:
                config.set_password(pwd)
            config.from_address = sanitize_text_input(request.form.get("from_address", "")).strip()
            config.from_name = sanitize_text_input(request.form.get("from_name", "")).strip()
            config.is_active = request.form.get("is_active") == "on"
            db.session.commit()
            flash("Configuration email enregistrée.", "success")
            return redirect(url_for("main.admin_email_config"))

        elif action == "test":
            success, msg = test_smtp_connection(config)
            admin = _current_user()
            if success and admin and admin.email:
                send_email(
                    admin.email,
                    "Test email — English Explorer",
                    "<p>La configuration SMTP fonctionne correctement ✓</p>",
                    "La configuration SMTP fonctionne correctement.",
                )
                msg += f" Un email de test a été envoyé à {admin.email}."
            test_result = {"success": success, "message": msg}

        elif action == "clear_password":
            config.set_password(None)
            db.session.commit()
            flash("Mot de passe SMTP supprimé.", "info")
            return redirect(url_for("main.admin_email_config"))

    return render_template(
        "admin/email_config.html",
        config=config,
        test_result=test_result,
    )


@bp.route("/admin/config")
@_admin_required
def admin_config_hub():
    """Hub de configuration système et email."""
    return render_template("admin/config_hub.html")


# ─── Unified Exercise Manager ─────────────────────────────────────────────────


def _preserve_filters(source) -> dict:
    keys = ("type", "q", "domain", "difficulty", "student_id", "date_from", "date_to")
    return {k: source.get(k) for k in keys if source.get(k)}


@bp.route("/parents/exercises")
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
                "edit_url": url_for(
                    "main.edit_exercise",
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
                "edit_url": url_for("main.edit_prepared_question", question_id=ex.id),
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
                "edit_url": url_for("main.edit_exercise_item", item_id=ex.id),
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
        difficulty_choices=DIFFICULTY_CHOICES,
        difficulty_display=DIFFICULTY_DISPLAY,
        filter_type=ex_type,
        filter_q=q,
        filter_domain=domain,
        filter_difficulty=difficulty,
        filter_student_id=student_id_raw,
        filter_date_from=date_from_raw,
        filter_date_to=date_to_raw,
    )


@bp.route(
    "/parents/prepared-questions/<int:question_id>/edit",
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
        return redirect(url_for("main.list_all_exercises"))

    return render_template(
        "edit_prepared_question.html",
        question=question,
        categories=categories,
        form_data=None,
    )


@bp.route(
    "/parents/exercise-items/<int:item_id>/edit",
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
                difficulty_choices=DIFFICULTY_CHOICES,
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
        return redirect(url_for("main.list_all_exercises"))

    return render_template(
        "edit_exercise_item.html",
        item=item,
        categories=categories,
        difficulty_choices=DIFFICULTY_CHOICES,
        form_data=None,
    )


@bp.route("/parents/exercises/bulk-edit", methods=["POST"])
@_parent_required
def bulk_edit_exercises():
    bulk_field = (request.form.get("bulk_field") or "").strip()
    bulk_value = (request.form.get("bulk_value") or "").strip()

    if bulk_field not in ("category", "difficulty"):
        flash("Champ de modification invalide.", "danger")
        return redirect(url_for("main.list_all_exercises"))

    all_categories = QuestionCategory.query.all()
    valid_cat_codes = {c.code for c in all_categories}
    valid_diffs = set(DIFFICULTY_LEVELS) | {"any"}

    if bulk_field == "category" and bulk_value not in valid_cat_codes:
        flash("Catégorie invalide.", "danger")
        return redirect(url_for("main.list_all_exercises"))
    if bulk_field == "difficulty" and bulk_value not in valid_diffs:
        flash("Niveau de difficulté invalide.", "danger")
        return redirect(url_for("main.list_all_exercises"))

    items_to_edit = []
    i = 0
    while True:
        item_type = request.form.get(f"item_{i}_type")
        item_id_raw = request.form.get(f"item_{i}_id")
        if item_type is None and item_id_raw is None:
            break
        try:
            items_to_edit.append((item_type, int(item_id_raw)))
        except (TypeError, ValueError):
            pass
        i += 1

    if not items_to_edit:
        flash("Aucun exercice sélectionné.", "warning")
        return redirect(url_for("main.list_all_exercises", **_preserve_filters(request.form)))

    cat_by_code = {c.code: c for c in all_categories}
    updated = 0
    for item_type, item_id in items_to_edit:
        if item_type == "session":
            if bulk_field == "category":
                ex = SessionExercise.query.get(item_id)
                if ex:
                    ex.category = bulk_value
                    updated += 1
        elif item_type == "prepared":
            if bulk_field == "category":
                ex = PreparedExerciseQuestion.query.get(item_id)
                if ex:
                    ex.category_code = bulk_value
                    updated += 1
        elif item_type == "bank":
            ex = ExerciseItem.query.get(item_id)
            if ex:
                if bulk_field == "category":
                    cat = cat_by_code.get(bulk_value)
                    if cat:
                        ex.category_id = cat.id
                        updated += 1
                elif bulk_field == "difficulty":
                    ex.difficulty = bulk_value
                    updated += 1

    db.session.commit()
    flash(f"{updated} exercice(s) modifié(s).", "success")
    return redirect(url_for("main.list_all_exercises", **_preserve_filters(request.form)))


@bp.route("/parents/exercise-items/<int:item_id>/toggle-active", methods=["POST"])
@_parent_required
def toggle_exercise_item_active(item_id: int):
    item = ExerciseItem.query.get_or_404(item_id)
    item.is_active = not item.is_active
    db.session.commit()
    flash("Exercice réactivé." if item.is_active else "Exercice désactivé.", "success" if item.is_active else "info")
    return redirect(url_for("main.list_all_exercises"))


def _parse_selected_items(form) -> List[Tuple[str, int]]:
    items = []
    i = 0
    while True:
        item_type = form.get(f"item_{i}_type")
        item_id_raw = form.get(f"item_{i}_id")
        if item_type is None and item_id_raw is None:
            break
        try:
            items.append((item_type, int(item_id_raw)))
        except (TypeError, ValueError):
            pass
        i += 1
    return items


@bp.route("/parents/exercises/batch-edit", methods=["POST"])
@_parent_required
def batch_edit_exercises():
    items_raw = _parse_selected_items(request.form)

    if not items_raw:
        flash("Aucun exercice sélectionné.", "warning")
        return redirect(url_for("main.list_all_exercises", **_preserve_filters(request.form)))

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
        return redirect(url_for("main.list_all_exercises"))

    categories = QuestionCategory.query.order_by(
        QuestionCategory.order_index, QuestionCategory.name
    ).all()
    back_url = url_for("main.list_all_exercises", **_preserve_filters(request.form))

    return render_template(
        "batch_edit_exercises.html",
        exercises=exercises,
        categories=categories,
        difficulty_choices=DIFFICULTY_CHOICES,
        difficulty_display=DIFFICULTY_DISPLAY,
        back_url=back_url,
    )


@bp.route("/parents/exercises/batch-save", methods=["POST"])
@_parent_required
def batch_save_exercises():
    back_url = request.form.get("back_url") or url_for("main.list_all_exercises")
    if not is_safe_url(back_url):
        back_url = url_for("main.list_all_exercises")

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
