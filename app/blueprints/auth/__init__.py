"""Blueprint ``auth`` : page d'accueil, login, register, logout et
réinitialisation de mot de passe.

Pas d'``url_prefix`` : les routes restent à la racine (``/``, ``/login``,
``/register``…) pour conserver les URL historiques.
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from uuid import uuid4

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

from ...extensions import db, limiter
from ...models import EmailConfig, PracticeSession, Student
from ...services.auth import (
    _current_user,
    _login_required,
    _login_user,
    _logout_user,
    is_safe_url,
)
from ...validators import (
    sanitize_text_input,
    validate_age,
    validate_email,
    validate_goals,
    validate_name,
    validate_password,
)


bp = Blueprint("auth", __name__)


# Import différé : validate_image_file vit encore dans routes.py tant que ce
# blueprint n'a pas son propre helper d'upload. On l'importe à la volée pour
# éviter un cycle ``routes -> blueprints.auth -> routes``.
def _validate_image_file(file):
    from ...routes import validate_image_file

    return validate_image_file(file)


# Les libellés de difficulté restent dans routes.py (utilisés par d'autres
# routes) ; pour l'index, on les ré-importe paresseusement.
def _difficulty_display() -> dict:
    from ...routes import DIFFICULTY_DISPLAY

    return DIFFICULTY_DISPLAY


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
    if user and user.is_parent():
        students = sorted(user.managed_students, key=lambda s: s.created_at, reverse=True)
        student_ids = {s.id for s in students}
        latest_sessions = (
            PracticeSession.query.filter(PracticeSession.student_id.in_(student_ids))
            .order_by(PracticeSession.started_at.desc())
            .limit(5)
            .all()
        ) if student_ids else []
    elif user and not user.is_admin():
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
        difficulty_labels=_difficulty_display(),
        can_manage_all=user.is_parent() or user.is_admin() if user else False,
    )


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def register():
    if _current_user():
        flash("Vous êtes déjà connecté·e.", "info")
        return redirect(url_for("auth.index"))

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
            return redirect(url_for("auth.register"))

        # Validation stricte du nom de famille
        if last_name and not validate_name(last_name):
            flash("Le nom de famille contient des caractères invalides ou est trop long.", "danger")
            return redirect(url_for("auth.register"))

        # Validation stricte de l'email
        if not validate_email(email_raw):
            flash("L'adresse e-mail n'est pas valide.", "danger")
            return redirect(url_for("auth.register"))

        if Student.query.filter_by(email=email_raw).first():
            flash("Cette adresse e-mail est déjà utilisée.", "danger")
            return redirect(url_for("auth.register"))

        # Validation stricte du mot de passe
        password_valid, password_message = validate_password(password)
        if not password_valid:
            flash(password_message, "danger")
            return redirect(url_for("auth.register"))

        if password != password_confirm:
            flash("La confirmation du mot de passe ne correspond pas.", "danger")
            return redirect(url_for("auth.register"))

        # Validation stricte de l'âge
        age_value = validate_age(age_raw)
        if age_raw and age_value is None:
            flash("L'âge doit être un nombre valide entre 3 et 120 ans.", "danger")
            return redirect(url_for("auth.register"))

        # Validation stricte des objectifs
        if goals and not validate_goals(goals):
            flash("Les objectifs contiennent du contenu invalide.", "danger")
            return redirect(url_for("auth.register"))

        avatar_file = request.files.get("avatar")
        avatar_filename: Optional[str] = None
        if avatar_file and avatar_file.filename:
            if not _validate_image_file(avatar_file):
                flash("Format d'image non pris en charge ou fichier invalide.", "danger")
                return redirect(url_for("auth.register"))

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
        return redirect(url_for("auth.index"))

    return render_template("auth/register.html")


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if _current_user():
        flash("Tu es déjà connecté·e.", "info")
        return redirect(url_for("auth.index"))

    if request.method == "GET":
        # Stocker le redirect cible en session pour ne pas l'exposer dans le HTML
        raw_next = request.args.get("next")
        if raw_next and is_safe_url(raw_next):
            session["login_next"] = raw_next
        return render_template("auth/login.html")

    # POST
    email_raw = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not email_raw or not password:
        flash("Identifiants incomplets.", "danger")
        return redirect(url_for("auth.login"))

    student = Student.query.filter_by(email=email_raw).first()
    if not student or not student.check_password(password):
        flash("E-mail ou mot de passe invalide.", "danger")
        return redirect(url_for("auth.login"))

    _login_user(student)
    flash("Connexion réussie !", "success")

    next_url = session.pop("login_next", None)
    if next_url and is_safe_url(next_url):
        return redirect(next_url)
    return redirect(url_for("auth.index"))


@bp.route("/logout", methods=["POST"])
@_login_required
def logout():
    _logout_user()
    flash("Tu es maintenant déconnecté·e.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def forgot_password():
    if _current_user():
        return redirect(url_for("auth.index"))

    if request.method == "GET":
        return render_template("auth/forgot_password.html")

    from ...email_service import generate_reset_token, send_password_reset_email

    email_raw = sanitize_text_input(request.form.get("email", "")).strip().lower()
    # Toujours afficher le même message pour éviter l'énumération d'emails
    flash(
        "Si cette adresse est associée à un compte, un email de réinitialisation vient d'être envoyé.",
        "info",
    )

    if not email_raw or not validate_email(email_raw):
        return redirect(url_for("auth.login"))

    email_config = EmailConfig.get_active()
    if email_config is None:
        flash("La réinitialisation par email n'est pas disponible pour le moment.", "warning")
        return redirect(url_for("auth.login"))

    student = Student.query.filter_by(email=email_raw).first()
    if student:
        token, token_hash = generate_reset_token()
        student.reset_token_hash = token_hash
        student.reset_token_expires_at = datetime.utcnow() + timedelta(hours=1)
        db.session.commit()
        reset_url = url_for("auth.reset_password", token=token, _external=True)
        send_password_reset_email(student, token, reset_url)

    return redirect(url_for("auth.login"))


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def reset_password(token: str):
    import hashlib

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    student = Student.query.filter(
        Student.reset_token_hash == token_hash,
        Student.reset_token_expires_at > datetime.utcnow(),
    ).first()

    if not student:
        flash("Lien de réinitialisation invalide ou expiré.", "danger")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "GET":
        return render_template("auth/reset_password.html", token=token)

    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    if new_password != confirm_password:
        flash("Les mots de passe ne correspondent pas.", "danger")
        return render_template("auth/reset_password.html", token=token)

    valid, msg = validate_password(new_password)
    if not valid:
        flash(msg, "danger")
        return render_template("auth/reset_password.html", token=token)

    student.set_password(new_password)
    student.reset_token_hash = None
    student.reset_token_expires_at = None
    db.session.commit()
    flash("Mot de passe réinitialisé avec succès. Vous pouvez vous connecter.", "success")
    return redirect(url_for("auth.login"))
