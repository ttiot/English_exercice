from collections import defaultdict
from datetime import datetime
from typing import Dict, List

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from . import db
from .config import Config
from .exercise_factory import ExercisePrompt, generate_default_exercises
from .models import PracticeSession, PreparedExercise, SessionExercise, Student

bp = Blueprint("main", __name__)


def _get_student_or_404(student_id: int) -> Student:
    student = Student.query.get(student_id)
    if not student:
        abort(404)
    return student


def _parent_authenticated() -> bool:
    return session.get("parent_authenticated", False)


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
    )


@bp.route("/students/new", methods=["GET", "POST"])
def create_student():
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        age = request.form.get("age")
        goals = request.form.get("goals", "").strip()

        if not first_name:
            flash("Le prénom est obligatoire.", "danger")
            return redirect(url_for("main.create_student"))

        try:
            age_value = int(age) if age else None
        except ValueError:
            flash("L'âge doit être un nombre.", "danger")
            return redirect(url_for("main.create_student"))

        student = Student(
            first_name=first_name,
            last_name=last_name or None,
            age=age_value,
            goals=goals or None,
        )
        db.session.add(student)
        db.session.commit()

        flash("Profil élève créé avec succès !", "success")
        return redirect(url_for("main.view_student", student_id=student.id))

    return render_template("student_form.html")


@bp.route("/students/<int:student_id>")
def view_student(student_id: int):
    student = _get_student_or_404(student_id)
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

    progress = {
        category: {
            "correct": stats["correct"],
            "total": stats["total"],
            "rate": (stats["correct"] / stats["total"] * 100) if stats["total"] else 0,
        }
        for category, stats in category_stats.items()
    }

    return render_template(
        "student_detail.html",
        student=student,
        sessions=sessions,
        progress=progress,
    )


@bp.route("/students/<int:student_id>/sessions/new", methods=["GET", "POST"])
def start_session(student_id: int):
    student = _get_student_or_404(student_id)
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
            total_questions=question_count,
        )
        db.session.add(session_obj)
        db.session.flush()

        targeted = (
            PreparedExercise.query.filter_by(is_used=False, student_id=student.id)
            .order_by(PreparedExercise.created_at.asc())
            .all()
        )
        general = (
            PreparedExercise.query.filter_by(is_used=False, student_id=None)
            .order_by(PreparedExercise.created_at.asc())
            .all()
        )

        prepared: List[PreparedExercise] = (targeted + general)[:question_count]

        exercises: List[ExercisePrompt] = []
        prepared_used: List[PreparedExercise] = []
        for prepared_ex in prepared:
            exercises.append(
                ExercisePrompt(
                    prompt=prepared_ex.prompt,
                    answer=prepared_ex.answer,
                    category=prepared_ex.category or "custom",
                )
            )
            prepared_used.append(prepared_ex)
            if len(exercises) >= question_count:
                break

        if len(exercises) < question_count:
            generated = generate_default_exercises(question_count - len(exercises))
            exercises.extend(generated)

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

        for prepared_ex in prepared_used:
            prepared_ex.is_used = True

        db.session.commit()

        return redirect(url_for("main.play_session", session_id=session_obj.id))

    return render_template("session_form.html", student=student)


@bp.route("/sessions/<int:session_id>", methods=["GET", "POST"])
def play_session(session_id: int):
    session_obj = PracticeSession.query.get_or_404(session_id)
    student = session_obj.student

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

    time_limit = session_obj.time_limit_minutes
    return render_template(
        "session_play.html",
        session_obj=session_obj,
        student=student,
        time_limit=time_limit,
    )


@bp.route("/sessions/<int:session_id>/summary")
def session_summary(session_id: int):
    session_obj = PracticeSession.query.get_or_404(session_id)
    return render_template("session_summary.html", session_obj=session_obj)


@bp.route("/parents/login", methods=["GET", "POST"])
def parent_login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == Config.PARENT_PORTAL_PASSWORD:
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
    prepared_exercises = (
        PreparedExercise.query.filter_by(is_used=False)
        .order_by(PreparedExercise.created_at.desc())
        .all()
    )

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
        prepared_exercises=prepared_exercises,
        students=students,
    )


@bp.route("/parents/prepared-exercises/new", methods=["POST"])
def create_prepared_exercise():
    if not _parent_authenticated():
        flash("Accès refusé.", "danger")
        return redirect(url_for("main.parent_login"))

    prompt = request.form.get("prompt", "").strip()
    answer = request.form.get("answer", "").strip()
    category = request.form.get("category", "custom").strip() or "custom"
    student_id = request.form.get("student_id")

    if not prompt or not answer:
        flash("Le contenu de l'exercice et la réponse sont obligatoires.", "danger")
        return redirect(url_for("main.parent_dashboard"))

    student_obj = None
    if student_id and student_id != "all":
        try:
            student_obj = Student.query.get(int(student_id))
        except (TypeError, ValueError):
            student_obj = None

    prepared_ex = PreparedExercise(
        prompt=prompt,
        answer=answer,
        category=category,
        student=student_obj,
    )
    db.session.add(prepared_ex)
    db.session.commit()

    flash("Exercice préparé enregistré.", "success")
    return redirect(url_for("main.parent_dashboard"))
