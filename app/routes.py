from collections import defaultdict
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

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

from . import db
from .config import Config
from .exercise_factory import (
    ExercisePrompt,
    DIFFICULTY_LABELS,
    DIFFICULTY_LEVELS,
    generate_default_exercises,
    normalize_difficulty,
)
from .models import (
    PracticeSession,
    PreparedExerciseQuestion,
    PreparedExerciseSet,
    QuestionCategory,
    SessionExercise,
    Student,
)

bp = Blueprint("main", __name__)

DIFFICULTY_DISPLAY = {**DIFFICULTY_LABELS, "prepared": "Parcours préparé"}
DIFFICULTY_CHOICES = [(value, DIFFICULTY_LABELS[value]) for value in DIFFICULTY_LEVELS]


def _load_user_from_session() -> Optional[Student]:
    user_id = session.get("user_id")
    if not user_id:
        return None
    return Student.query.get(user_id)


def _current_user() -> Optional[Student]:
    if not hasattr(g, "current_user"):
        g.current_user = _load_user_from_session()
    return g.current_user


def _login_user(user: Student) -> None:
    session["user_id"] = user.id
    session.permanent = True
    g.current_user = user


def _logout_user() -> None:
    session.pop("user_id", None)
    g.current_user = None


def _get_student_or_404(student_id: int) -> Student:
    student = Student.query.get(student_id)
    if not student:
        abort(404)
    return student


def _login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        user = _current_user()
        if not user:
            next_url = request.url if request.method == "GET" else url_for("main.index")
            return redirect(url_for("main.login", next=next_url))
        return view(*args, **kwargs)

    return wrapped_view


def _parent_required(view):
    @wraps(view)
    @_login_required
    def wrapped_view(*args, **kwargs):
        user = _current_user()
        if not user or not (user.is_parent() or user.is_admin()):
            flash("Accès réservé aux parents ou à l'administrateur.", "warning")
            return redirect(url_for("main.index"))
        return view(*args, **kwargs)

    return wrapped_view


def _admin_required(view):
    @wraps(view)
    @_login_required
    def wrapped_view(*args, **kwargs):
        user = _current_user()
        if not user or not user.is_admin():
            flash("Seul l'administrateur peut effectuer cette action.", "warning")
            return redirect(url_for("main.index"))
        return view(*args, **kwargs)

    return wrapped_view


@bp.before_app_request
def require_login() -> Optional[None]:
    endpoint = request.endpoint or ""
    if endpoint in {"main.login", "main.register", "main.logout"}:
        return None
    if endpoint.startswith("static"):
        return None

    user = _current_user()
    if not user:
        next_url = request.url if request.method == "GET" else url_for("main.index")
        return redirect(url_for("main.login", next=next_url))
    return None


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


@bp.route("/")
@_login_required
def index():
    user = _current_user()
    students = (
        Student.query.filter_by(role="student")
        .order_by(Student.created_at.desc())
        .all()
    )
    latest_sessions = (
        PracticeSession.query.order_by(PracticeSession.started_at.desc()).limit(5).all()
    )
    if user and not (user.is_parent() or user.is_admin()):
        students = [student for student in students if student.id == user.id]
        latest_sessions = (
            PracticeSession.query.filter_by(student_id=user.id)
            .order_by(PracticeSession.started_at.desc())
            .limit(5)
            .all()
        )
    return render_template(
        "index.html",
        students=students,
        latest_sessions=latest_sessions,
        difficulty_labels=DIFFICULTY_DISPLAY,
        can_manage_all=user.is_parent() or user.is_admin() if user else False,
    )


@bp.route("/register", methods=["GET", "POST"])
def register():
    if _current_user():
        flash("Vous êtes déjà connecté·e.", "info")
        return redirect(url_for("main.index"))

    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip() or None
        email_raw = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        age_raw = request.form.get("age", "").strip()
        goals = request.form.get("goals", "").strip() or None

        if not first_name:
            flash("Le prénom est obligatoire.", "danger")
            return redirect(url_for("main.register"))

        if not email_raw:
            flash("L'adresse e-mail est obligatoire.", "danger")
            return redirect(url_for("main.register"))

        if Student.query.filter_by(email=email_raw).first():
            flash("Cette adresse e-mail est déjà utilisée.", "danger")
            return redirect(url_for("main.register"))

        if len(password) < 8:
            flash("Le mot de passe doit contenir au moins 8 caractères.", "danger")
            return redirect(url_for("main.register"))

        if password != password_confirm:
            flash("La confirmation du mot de passe ne correspond pas.", "danger")
            return redirect(url_for("main.register"))

        try:
            age_value = int(age_raw) if age_raw else None
        except ValueError:
            flash("L'âge doit être un nombre.", "danger")
            return redirect(url_for("main.register"))

        avatar_file = request.files.get("avatar")
        avatar_filename: Optional[str] = None
        if avatar_file and avatar_file.filename:
            sanitized = secure_filename(avatar_file.filename)
            extension = sanitized.rsplit(".", 1)[-1].lower() if "." in sanitized else ""
            if extension not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
                flash("Format d'image non pris en charge.", "danger")
                return redirect(url_for("main.register"))

            avatar_filename = f"{uuid4().hex}.{extension}"
            destination = Path(current_app.config["UPLOAD_FOLDER"]) / avatar_filename
            avatar_file.save(destination)

        student = Student(
            first_name=first_name,
            last_name=last_name,
            email=email_raw,
            age=age_value,
            goals=goals,
            role="student",
            avatar_filename=avatar_filename,
        )
        student.set_password(password)

        db.session.add(student)
        db.session.commit()

        _login_user(student)
        flash("Bienvenue ! Ton compte élève a été créé.", "success")
        return redirect(url_for("main.index"))

    return render_template("auth/register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if _current_user():
        flash("Tu es déjà connecté·e.", "info")
        return redirect(url_for("main.index"))

    if request.method == "POST":
        email_raw = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        next_url = request.form.get("next")

        if not email_raw or not password:
            flash("Identifiants incomplets.", "danger")
            return redirect(url_for("main.login"))

        student = Student.query.filter_by(email=email_raw).first()
        if not student or not student.check_password(password):
            flash("E-mail ou mot de passe invalide.", "danger")
            return redirect(url_for("main.login"))

        _login_user(student)
        flash("Connexion réussie !", "success")

        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return redirect(url_for("main.index"))

    next_url = request.args.get("next") if request.method == "GET" else None
    return render_template("auth/login.html", next_url=next_url)


@bp.route("/logout", methods=["POST"])
@_login_required
def logout():
    _logout_user()
    flash("Tu es maintenant déconnecté·e.", "info")
    return redirect(url_for("main.login"))


@bp.route("/students/new", methods=["GET", "POST"])
@_parent_required
def create_student():
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip() or None
        email_raw = request.form.get("email", "").strip().lower()
        age_raw = request.form.get("age")
        goals = request.form.get("goals", "").strip() or None
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")

        if not first_name:
            flash("Le prénom est obligatoire.", "danger")
            return redirect(url_for("main.create_student"))

        if not email_raw:
            flash("L'adresse e-mail est obligatoire.", "danger")
            return redirect(url_for("main.create_student"))

        if Student.query.filter_by(email=email_raw).first():
            flash("Cette adresse e-mail est déjà utilisée.", "danger")
            return redirect(url_for("main.create_student"))

        if len(password) < 8:
            flash("Le mot de passe doit contenir au moins 8 caractères.", "danger")
            return redirect(url_for("main.create_student"))

        if password != password_confirm:
            flash("La confirmation du mot de passe ne correspond pas.", "danger")
            return redirect(url_for("main.create_student"))

        try:
            age_value = int(age_raw) if age_raw else None
        except ValueError:
            flash("L'âge doit être un nombre.", "danger")
            return redirect(url_for("main.create_student"))

        avatar_file = request.files.get("avatar")
        avatar_filename: Optional[str] = None
        if avatar_file and avatar_file.filename:
            sanitized = secure_filename(avatar_file.filename)
            extension = sanitized.rsplit(".", 1)[-1].lower() if "." in sanitized else ""
            if extension not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
                flash("Format d'image non pris en charge.", "danger")
                return redirect(url_for("main.create_student"))

            avatar_filename = f"{uuid4().hex}.{extension}"
            destination = Path(current_app.config["UPLOAD_FOLDER"]) / avatar_filename
            avatar_file.save(destination)

        student = Student(
            first_name=first_name,
            last_name=last_name,
            email=email_raw,
            age=age_value,
            goals=goals,
            avatar_filename=avatar_filename,
            role="student",
        )
        student.set_password(password)
        db.session.add(student)
        db.session.commit()

        flash("Profil élève créé avec succès !", "success")
        return redirect(url_for("main.view_student", student_id=student.id))

    return render_template("student_form.html")

@bp.route("/students/<int:student_id>")
@_login_required
def view_student(student_id: int):
    student = _get_student_or_404(student_id)
    user = _current_user()

    parent_ok = user.is_parent() or user.is_admin()
    student_ok = user.id == student.id
    if not (student_ok or parent_ok):
        flash("Accès refusé pour ce profil.", "danger")
        return redirect(url_for("main.index"))

    sessions = (
        PracticeSession.query.filter_by(student_id=student.id)
        .order_by(PracticeSession.started_at.desc())
        .all()
    )

    category_stats: Dict[str, Dict[str, float]] = defaultdict(lambda: {"correct": 0, "total": 0})
    for session_obj in sessions:
        for exercise in session_obj.exercises:
            category_stats[exercise.category]["total"] += 1
            if exercise.is_correct:
                category_stats[exercise.category]["correct"] += 1

    category_lookup = {
        category.code: category.name for category in QuestionCategory.query.order_by(QuestionCategory.name)
    }

    progress = [
        {
            "code": category,
            "label": category_lookup.get(category, category.replace("_", " ").title()),
            "correct": stats["correct"],
            "total": stats["total"],
            "rate": (stats["correct"] / stats["total"] * 100) if stats["total"] else 0,
        }
        for category, stats in category_stats.items()
    ]

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
        return redirect(url_for("main.index"))

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
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        email_raw = request.form.get("email", "").strip().lower()
        goals = request.form.get("goals", "").strip()
        age_raw = request.form.get("age", "").strip()
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

        avatar_file = request.files.get("avatar")
        new_avatar_filename: Optional[str] = None
        if avatar_file and avatar_file.filename:
            sanitized = secure_filename(avatar_file.filename)
            extension = sanitized.rsplit(".", 1)[-1].lower() if "." in sanitized else ""
            if extension not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
                flash("Format d'image non pris en charge.", "danger")
                return redirect(url_for("main.manage_student", student_id=student.id))

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

        db.session.commit()
        flash("Profil mis à jour.", "success")
        return redirect(url_for("main.manage_student", student_id=student.id))

    return render_template(
        "student_settings.html",
        student=student,
        parent_ok=parent_ok,
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
        difficulty_choice = request.form.get("difficulty", DIFFICULTY_LEVELS[0])
        difficulty_value = normalize_difficulty(difficulty_choice)
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

        session_obj = PracticeSession(
            student_id=student.id,
            time_limit_minutes=time_limit_value,
            time_limit_seconds=(time_limit_value * 60) if time_limit_value else None,
            total_questions=question_count,
            difficulty=difficulty_value,
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

            for index, question in enumerate(prepared_set.questions):
                db.session.add(
                    SessionExercise(
                        session_id=session_obj.id,
                        prompt=question.prompt,
                        correct_answer=question.answer,
                        category=question.category_code,
                        display_order=index,
                    )
                )
            session_obj.total_questions = len(prepared_set.questions)
            prepared_set.mark_used()
        else:
            exercises = generate_default_exercises(question_count, difficulty=difficulty_value)
            for index, exercise in enumerate(exercises):
                db.session.add(
                    SessionExercise(
                        session_id=session_obj.id,
                        prompt=exercise.prompt,
                        correct_answer=exercise.answer,
                        category=exercise.category,
                        display_order=index,
                    )
                )
            session_obj.total_questions = len(exercises)

        db.session.commit()

        return redirect(url_for("main.play_session", session_id=session_obj.id))

    selected_difficulty = normalize_difficulty(request.args.get("difficulty"))
    return render_template(
        "session_form.html",
        student=student,
        difficulty_choices=DIFFICULTY_CHOICES,
        selected_difficulty=selected_difficulty,
        difficulty_labels=DIFFICULTY_DISPLAY,
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
            exercise.is_correct = user_answer.lower() == exercise.correct_answer.lower()
            if exercise.is_correct:
                correct_answers += 1
        session_obj.completed_at = datetime.utcnow()
        session_obj.correct_answers = correct_answers
        db.session.commit()

        flash("Session terminée ! Voici ton score.", "success")
        return redirect(url_for("main.session_summary", session_id=session_obj.id))

    time_limit = session_obj.time_limit_seconds
    if not time_limit and session_obj.time_limit_minutes:
        time_limit = session_obj.time_limit_minutes * 60
    return render_template(
        "session_play.html",
        session_obj=session_obj,
        student=student,
        time_limit=time_limit,
        difficulty_labels=DIFFICULTY_DISPLAY,
    )


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
    return render_template(
        "session_summary.html",
        session_obj=session_obj,
        category_lookup=category_lookup,
        difficulty_labels=DIFFICULTY_DISPLAY,
    )


@bp.route("/parents/dashboard")
@_parent_required
def parent_dashboard():
    user = _current_user()
    students = Student.query.filter_by(role="student").order_by(Student.first_name).all()
    prepared_sets = (
        PreparedExerciseSet.query.filter_by(is_used=False)
        .order_by(PreparedExerciseSet.created_at.desc())
        .all()
    )
    categories = QuestionCategory.query.order_by(QuestionCategory.name).all()

    stats = []
    for student in students:
        sessions = PracticeSession.query.filter_by(student_id=student.id).all()
        total_sessions = len(sessions)
        total_questions = sum(session.total_questions or 0 for session in sessions)
        total_correct = sum(session.correct_answers or 0 for session in sessions)
        average_score = (total_correct / total_questions * 100) if total_questions else 0
        stats.append(
            {
                "student": student,
                "total_sessions": total_sessions,
                "average_score": round(average_score, 1) if average_score else 0,
            }
        )

    all_users = []
    if user and user.is_admin():
        all_users = Student.query.order_by(Student.first_name, Student.last_name).all()

    return render_template(
        "parent_dashboard.html",
        stats=stats,
        prepared_sets=prepared_sets,
        students=students,
        categories=categories,
        all_users=all_users,
    )


@bp.route("/parents/prepared-exercises/new", methods=["GET", "POST"])
@_parent_required
def create_prepared_exercise():
    students = Student.query.filter_by(role="student").order_by(Student.first_name).all()
    categories = QuestionCategory.query.order_by(QuestionCategory.name).all()

    if request.method == "POST":
        title = request.form.get("title", "").strip() or "Exercice préparé"
        student_id = request.form.get("student_id")
        use_time_limit = request.form.get("use_time_limit") == "on"
        minutes_raw = request.form.get("limit_minutes", "0").strip()
        seconds_raw = request.form.get("limit_seconds", "0").strip()

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
            prompt_clean = prompt_text.strip()
            answer_clean = answer_text.strip()
            category_code = (category_code or "custom").strip() or "custom"
            if prompt_clean and answer_clean:
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

    student_id = session_obj.student_id

    db.session.delete(session_obj)
    db.session.commit()

    flash("La session a été supprimée.", "success")

    next_url = request.form.get("next")
    if next_url and next_url.startswith("/"):
        return redirect(next_url)

    return redirect(url_for("main.view_student", student_id=student_id))


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
        return redirect(url_for("main.parent_dashboard"))

    target.role = new_role
    db.session.commit()
    flash("Rôle utilisateur mis à jour.", "success")
    return redirect(url_for("main.parent_dashboard"))
