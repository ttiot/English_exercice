from collections import defaultdict
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4
from urllib.parse import urlparse, urljoin

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

from . import db
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
    PracticeSession,
    PreparedExerciseQuestion,
    PreparedExerciseSet,
    QuestionCategory,
    SessionExercise,
    SkillPrerequisite,
    Student,
    StudentSkillProgress,
)
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
DOMAIN_CHOICES = [
    ("vocabulary", "Vocabulaire"),
    ("grammar", "Grammaire"),
    ("comprehension", "Compréhension"),
    ("production", "Production"),
    ("culture", "Culture"),
]


def is_safe_url(target):
    """Vérifier qu'une URL de redirection est sûre"""
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and \
           ref_url.netloc == test_url.netloc


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


def _parse_domain_list(raw_values: List[str]) -> str:
    allowed = {code for code, _ in DOMAIN_CHOICES}
    filtered = [value for value in raw_values if value in allowed]
    return ",".join(filtered)


def _domain_list(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _grade_rank(value: Optional[str]) -> int:
    mapping = {"6e": 1, "5e": 2}
    return mapping.get(value or "", 0)


def _cefr_rank(value: Optional[str]) -> int:
    mapping = {"A1": 1, "A2": 2}
    return mapping.get(value or "", 0)


def _difficulty_from_cefr(level: Optional[str]) -> str:
    mapping = {"A1": "beginner", "A2": "intermediate"}
    if level in mapping:
        return mapping[level]
    return DIFFICULTY_LEVELS[0]


def _category_in_target(category: QuestionCategory, student: Student) -> bool:
    if student.target_cefr_level and category.cecrl_level:
        if _cefr_rank(category.cecrl_level) > _cefr_rank(student.target_cefr_level):
            return False
    if student.target_grade and category.grade_level:
        if _grade_rank(category.grade_level) > _grade_rank(student.target_grade):
            return False
        if student.target_trimester and category.trimester:
            if category.grade_level == student.target_grade and category.trimester > student.target_trimester:
                return False
    return True


def _load_progress_map(student_id: int) -> Dict[int, StudentSkillProgress]:
    entries = StudentSkillProgress.query.filter_by(student_id=student_id).all()
    return {entry.category_id: entry for entry in entries}


def _build_prerequisite_map() -> Dict[int, List[SkillPrerequisite]]:
    prerequisites = SkillPrerequisite.query.all()
    grouped: Dict[int, List[SkillPrerequisite]] = {}
    for item in prerequisites:
        grouped.setdefault(item.category_id, []).append(item)
    return grouped


def _is_category_unlocked(
    category: QuestionCategory,
    progress_map: Dict[int, StudentSkillProgress],
    prereq_map: Dict[int, List[SkillPrerequisite]],
) -> bool:
    if category.unlocked_by_default:
        return True
    prerequisites = prereq_map.get(category.id, [])
    if not prerequisites:
        return False
    for prereq in prerequisites:
        progress = progress_map.get(prereq.prerequisite_id)
        if not progress or progress.mastery < prereq.min_mastery:
            return False
    return True


def _category_priority(
    category: QuestionCategory,
    progress: Optional[StudentSkillProgress],
    preferred_domains: List[str],
) -> float:
    base = 50.0
    if not progress or progress.total_attempts == 0:
        base = 90.0
    else:
        mastery = progress.mastery or 0.0
        base = max(10.0, 100.0 - mastery)
        if progress.last_practiced:
            days_since = max(0, (datetime.utcnow() - progress.last_practiced).days)
            base += min(days_since * 4.0, 40.0)
        if mastery < 60.0:
            base += 15.0
    if category.domain in preferred_domains:
        base *= 1.2
    return base


def _review_interval_days(mastery: float) -> int:
    if mastery < 50:
        return 1
    if mastery < 70:
        return 3
    if mastery < 85:
        return 7
    return 14


def _recommend_difficulty(student: Student) -> str:
    baseline = _difficulty_from_cefr(student.target_cefr_level)
    latest_session = (
        PracticeSession.query.filter_by(student_id=student.id)
        .order_by(PracticeSession.started_at.desc())
        .first()
    )
    if latest_session and latest_session.difficulty in DIFFICULTY_LEVELS:
        baseline = latest_session.difficulty
    recent_sessions = (
        PracticeSession.query.filter_by(student_id=student.id)
        .order_by(PracticeSession.started_at.desc())
        .limit(5)
        .all()
    )
    accuracy_samples = []
    time_samples = []
    for session_obj in recent_sessions:
        if session_obj.total_questions:
            accuracy_samples.append(session_obj.correct_answers / session_obj.total_questions)
        if session_obj.duration_seconds and session_obj.total_questions:
            time_samples.append(session_obj.duration_seconds / session_obj.total_questions)
    if not accuracy_samples:
        return baseline

    avg_accuracy = sum(accuracy_samples) / len(accuracy_samples)
    avg_time = sum(time_samples) / len(time_samples) if time_samples else None

    level_index = DIFFICULTY_LEVELS.index(baseline)
    if avg_accuracy >= 0.85 and (avg_time is None or avg_time <= 35):
        level_index = min(level_index + 1, len(DIFFICULTY_LEVELS) - 1)
    elif avg_accuracy <= 0.6 or (avg_time is not None and avg_time >= 60):
        level_index = max(level_index - 1, 0)
    return DIFFICULTY_LEVELS[level_index]


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
        first_name = sanitize_text_input(request.form.get("first_name", ""))
        last_name = sanitize_text_input(request.form.get("last_name", "")) or None
        email_raw = sanitize_text_input(request.form.get("email", "")).lower()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        age_raw = request.form.get("age", "").strip()
        goals = sanitize_text_input(request.form.get("goals", "")) or None

        # Validation stricte du prénom
        if not validate_name(first_name):
            flash("Le prénom contient des caractères invalides ou est trop long.", "danger")
            return redirect(url_for("main.register"))

        # Validation stricte du nom de famille
        if last_name and not validate_name(last_name):
            flash("Le nom de famille contient des caractères invalides ou est trop long.", "danger")
            return redirect(url_for("main.register"))

        # Validation stricte de l'email
        if not validate_email(email_raw):
            flash("L'adresse e-mail n'est pas valide.", "danger")
            return redirect(url_for("main.register"))

        if Student.query.filter_by(email=email_raw).first():
            flash("Cette adresse e-mail est déjà utilisée.", "danger")
            return redirect(url_for("main.register"))

        # Validation stricte du mot de passe
        password_valid, password_message = validate_password(password)
        if not password_valid:
            flash(password_message, "danger")
            return redirect(url_for("main.register"))

        if password != password_confirm:
            flash("La confirmation du mot de passe ne correspond pas.", "danger")
            return redirect(url_for("main.register"))

        # Validation stricte de l'âge
        age_value = validate_age(age_raw)
        if age_raw and age_value is None:
            flash("L'âge doit être un nombre valide entre 3 et 120 ans.", "danger")
            return redirect(url_for("main.register"))

        # Validation stricte des objectifs
        if goals and not validate_goals(goals):
            flash("Les objectifs contiennent du contenu invalide.", "danger")
            return redirect(url_for("main.register"))

        avatar_file = request.files.get("avatar")
        avatar_filename: Optional[str] = None
        if avatar_file and avatar_file.filename:
            if not validate_image_file(avatar_file):
                flash("Format d'image non pris en charge ou fichier invalide.", "danger")
                return redirect(url_for("main.register"))

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

        if next_url and is_safe_url(next_url):
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
        return redirect(url_for("main.index"))

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
        default_adaptive=True,
        default_skill_path=True,
        recommended_difficulty=_recommend_difficulty(student),
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
        if session_obj.started_at:
            session_obj.duration_seconds = int(
                (session_obj.completed_at - session_obj.started_at).total_seconds()
            )
        _update_progress_from_session(session_obj)
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
