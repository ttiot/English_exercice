from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from flask import (
    Blueprint,
    abort,
    flash,
    current_app,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from werkzeug.utils import secure_filename

from . import db
from .config import Config
from .exercise_factory import ExercisePrompt, generate_default_exercises
from .models import (
    ParentCredential,
    PracticeSession,
    PreparedExerciseQuestion,
    PreparedExerciseSet,
    QuestionCategory,
    SessionExercise,
    Student,
)

bp = Blueprint("main", __name__)


def _get_student_or_404(student_id: int) -> Student:
    student = Student.query.get(student_id)
    if not student:
        abort(404)
    return student


def _parent_authenticated() -> bool:
    return session.get("parent_authenticated", False)


def _student_authenticated(student_id: int) -> bool:
    unlocked = session.get("unlocked_students", [])
    return str(student_id) in unlocked


def _unlock_student_session(student_id: int) -> None:
    unlocked = session.get("unlocked_students", [])
    student_key = str(student_id)
    if student_key not in unlocked:
        unlocked.append(student_key)
        session["unlocked_students"] = unlocked
        session.modified = True


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
def index():
    students = Student.query.order_by(Student.created_at.desc()).all()
    latest_sessions = (
        PracticeSession.query.order_by(PracticeSession.started_at.desc()).limit(5).all()
    )
    return render_template(
        "index.html",
        students=students,
        latest_sessions=latest_sessions,
        unlocked_students={int(s) for s in session.get("unlocked_students", [])},
    )


@bp.route("/students/new", methods=["GET", "POST"])
def create_student():
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        age = request.form.get("age")
        goals = request.form.get("goals", "").strip()
        pin = request.form.get("pin", "").strip()
        pin_confirm = request.form.get("pin_confirm", "").strip()

        if not first_name:
            flash("Le prénom est obligatoire.", "danger")
            return redirect(url_for("main.create_student"))

        if not pin or not pin.isdigit() or len(pin) != 4:
            flash("Le code PIN doit contenir exactement 4 chiffres.", "danger")
            return redirect(url_for("main.create_student"))

        if pin != pin_confirm:
            flash("La confirmation du code PIN ne correspond pas.", "danger")
            return redirect(url_for("main.create_student"))

        try:
            age_value = int(age) if age else None
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
            last_name=last_name or None,
            age=age_value,
            goals=goals or None,
            avatar_filename=avatar_filename,
        )
        student.set_pin(pin)
        db.session.add(student)
        db.session.commit()

        _unlock_student_session(student.id)
        flash("Profil élève créé avec succès !", "success")
        return redirect(url_for("main.view_student", student_id=student.id))

    return render_template("student_form.html")


@bp.route("/students/<int:student_id>/unlock", methods=["GET", "POST"])
def unlock_student(student_id: int):
    student = _get_student_or_404(student_id)

    if _parent_authenticated() or _student_authenticated(student_id):
        return redirect(url_for("main.view_student", student_id=student_id))

    if request.method == "POST":
        pin = request.form.get("pin", "").strip()
        if student.check_pin(pin):
            _unlock_student_session(student_id)
            flash("Profil débloqué, amuse-toi bien !", "success")
            return redirect(url_for("main.view_student", student_id=student_id))
        flash("Code incorrect. Réessaie.", "danger")

    return render_template("student_unlock.html", student=student)


@bp.route("/students/<int:student_id>")
def view_student(student_id: int):
    student = _get_student_or_404(student_id)
    parent_ok = _parent_authenticated()
    student_ok = _student_authenticated(student_id)
    if not (student_ok or parent_ok):
        flash("Entre ton code secret pour accéder à ton profil.", "warning")
        return redirect(url_for("main.unlock_student", student_id=student_id))

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
    )


@bp.route("/students/<int:student_id>/settings", methods=["GET", "POST"])
def manage_student(student_id: int):
    student = _get_student_or_404(student_id)

    parent_ok = _parent_authenticated()
    student_ok = _student_authenticated(student_id)
    if not (parent_ok or student_ok):
        flash("Débloque d'abord le profil avec le code PIN.", "warning")
        return redirect(url_for("main.unlock_student", student_id=student_id))

    if request.method == "POST":
        action = request.form.get("action", "profile")

        if action == "pin":
            current_pin = request.form.get("current_pin", "").strip()
            new_pin = request.form.get("new_pin", "").strip()
            confirm_pin = request.form.get("confirm_pin", "").strip()

            if not new_pin or not new_pin.isdigit() or len(new_pin) != 4:
                flash("Le nouveau code PIN doit contenir exactement 4 chiffres.", "danger")
                return redirect(url_for("main.manage_student", student_id=student.id))

            if new_pin != confirm_pin:
                flash("La confirmation du code PIN ne correspond pas.", "danger")
                return redirect(url_for("main.manage_student", student_id=student.id))

            if not parent_ok and not student.check_pin(current_pin):
                flash("L'ancien code PIN est incorrect.", "danger")
                return redirect(url_for("main.manage_student", student_id=student.id))

            student.set_pin(new_pin)
            db.session.commit()
            flash("Code PIN mis à jour avec succès.", "success")
            return redirect(url_for("main.manage_student", student_id=student.id))

        # Default to profile update
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        goals = request.form.get("goals", "").strip()
        age_raw = request.form.get("age", "").strip()
        remove_avatar = request.form.get("remove_avatar") == "on"

        if not first_name:
            flash("Le prénom est obligatoire.", "danger")
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
def start_session(student_id: int):
    student = _get_student_or_404(student_id)
    if not (_student_authenticated(student_id) or _parent_authenticated()):
        flash("Débloque d'abord le profil avec le code PIN.", "warning")
        return redirect(url_for("main.unlock_student", student_id=student_id))

    if request.method == "POST":
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
            exercises = generate_default_exercises(question_count)
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

    return render_template("session_form.html", student=student)


@bp.route("/sessions/<int:session_id>", methods=["GET", "POST"])
def play_session(session_id: int):
    session_obj = PracticeSession.query.get_or_404(session_id)
    student = session_obj.student

    if not student:
        abort(404)

    parent_ok = _parent_authenticated()
    student_ok = _student_authenticated(student.id)
    if not (parent_ok or student_ok):
        flash("Débloque d'abord le profil avec le code PIN.", "warning")
        return redirect(url_for("main.unlock_student", student_id=student.id))

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
    )


@bp.route("/sessions/<int:session_id>/summary")
def session_summary(session_id: int):
    session_obj = PracticeSession.query.get_or_404(session_id)
    student = session_obj.student
    if not student:
        abort(404)

    parent_ok = _parent_authenticated()
    student_ok = _student_authenticated(student.id)
    if not (parent_ok or student_ok):
        flash("Débloque d'abord le profil avec le code PIN.", "warning")
        return redirect(url_for("main.unlock_student", student_id=student.id))

    category_lookup = {
        category.code: category.name for category in QuestionCategory.query.all()
    }
    return render_template(
        "session_summary.html",
        session_obj=session_obj,
        category_lookup=category_lookup,
    )


@bp.route("/parents/login", methods=["GET", "POST"])
def parent_login():
    if request.method == "POST":
        password = request.form.get("password", "")
        credential = ParentCredential.query.first()
        if credential and credential.check_password(password):
            session["parent_authenticated"] = True
            flash("Connexion réussie.", "success")
            return redirect(url_for("main.parent_dashboard"))
        flash("Mot de passe incorrect.", "danger")
    return render_template("parent_login.html")


@bp.route("/parents/logout")
def parent_logout():
    session.pop("parent_authenticated", None)
    flash("Vous êtes déconnecté.", "info")
    return redirect(url_for("main.index"))


@bp.route("/parents/dashboard")
def parent_dashboard():
    if not _parent_authenticated():
        flash("Veuillez vous connecter.", "warning")
        return redirect(url_for("main.parent_login"))

    students = Student.query.order_by(Student.first_name).all()
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

    return render_template(
        "parent_dashboard.html",
        stats=stats,
        prepared_sets=prepared_sets,
        students=students,
        categories=categories,
    )


@bp.route("/parents/prepared-exercises/new", methods=["GET", "POST"])
def create_prepared_exercise():
    if not _parent_authenticated():
        flash("Accès refusé.", "danger")
        return redirect(url_for("main.parent_login"))

    students = Student.query.order_by(Student.first_name).all()
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
def create_category():
    if not _parent_authenticated():
        flash("Accès refusé.", "danger")
        return redirect(url_for("main.parent_login"))

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
def rename_category(category_id: int):
    if not _parent_authenticated():
        flash("Accès refusé.", "danger")
        return redirect(url_for("main.parent_login"))

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
def delete_category(category_id: int):
    if not _parent_authenticated():
        flash("Accès refusé.", "danger")
        return redirect(url_for("main.parent_login"))

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


@bp.route("/parents/password", methods=["POST"])
def update_parent_password():
    if not _parent_authenticated():
        flash("Accès refusé.", "danger")
        return redirect(url_for("main.parent_login"))

    new_password = request.form.get("new_password", "").strip()
    confirm_password = request.form.get("confirm_password", "").strip()

    if len(new_password) < 6:
        flash("Le mot de passe doit contenir au moins 6 caractères.", "danger")
        return redirect(url_for("main.parent_dashboard"))

    if new_password != confirm_password:
        flash("La confirmation ne correspond pas.", "danger")
        return redirect(url_for("main.parent_dashboard"))

    credential = ParentCredential.query.first()
    if not credential:
        credential = ParentCredential()
        db.session.add(credential)

    credential.set_password(new_password)
    db.session.commit()
    flash("Mot de passe mis à jour.", "success")
    return redirect(url_for("main.parent_dashboard"))


@bp.route("/parents/sessions/<int:session_id>/delete", methods=["POST"])
def delete_session(session_id: int):
    if not _parent_authenticated():
        flash("Accès refusé.", "danger")
        return redirect(url_for("main.parent_login"))

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
