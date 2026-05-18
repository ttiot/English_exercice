"""Routes ``/admin/users/*`` : gestion des comptes (rôles, impersonation, CRUD).
"""

from pathlib import Path
from typing import Optional
from uuid import uuid4

from flask import (
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

from ...extensions import db
from ...models import (
    AICallLog,
    PreparedExercise,
    PreparedExerciseSet,
    ReviewPlan,
    Student,
    StudentBadge,
    StudentSkillProgress,
    WeeklyGoal,
)
from ...services.auth import (
    _admin_required,
    _current_user,
    _get_student_or_404,
)
from ...services.curriculum import (
    DOMAIN_CHOICES,
    _domain_list,
    _parse_domain_list,
)
from ...validators import (
    sanitize_text_input,
    validate_age,
    validate_email,
    validate_goals,
    validate_name,
    validate_password,
)
from . import bp


def _constants():
    from ...routes import CEFR_LEVELS, GRADE_LEVELS, TRIMESTER_CHOICES

    return CEFR_LEVELS, GRADE_LEVELS, TRIMESTER_CHOICES


def _validate_image_file(file):
    from ...routes import validate_image_file

    return validate_image_file(file)


def _delete_avatar_file(filename):
    from ...routes import _delete_avatar_file as impl

    return impl(filename)


@bp.route("/users")
@_admin_required
def admin_users():
    """Gestion des comptes utilisateurs."""
    all_users = Student.query.order_by(Student.first_name, Student.last_name).all()
    return render_template("admin/users.html", all_users=all_users)


@bp.route("/users/<int:user_id>/role", methods=["POST"])
@_admin_required
def update_user_role(user_id: int):
    target = _get_student_or_404(user_id)
    new_role = request.form.get("role", "student").strip()

    if new_role not in {"student", "parent", "admin"}:
        flash("Type de compte invalide.", "danger")
        return redirect(url_for("parents.parent_dashboard"))

    current_user = _current_user()
    if current_user.id == target.id and new_role != "admin":
        flash("Tu ne peux pas retirer ton propre rôle d'administrateur.", "warning")
        return redirect(url_for("admin.admin_users"))

    target.role = new_role
    db.session.commit()
    flash("Rôle utilisateur mis à jour.", "success")
    return redirect(url_for("admin.admin_users"))


@bp.route("/users/<int:user_id>/impersonate", methods=["POST"])
@_admin_required
def impersonate_user(user_id: int):
    if session.get("original_admin_id"):
        flash("Terminez d'abord la session d'impersonnification en cours.", "warning")
        return redirect(url_for("admin.admin_users"))
    target = _get_student_or_404(user_id)
    session["original_admin_id"] = session["user_id"]
    session["user_id"] = target.id
    g.pop("current_user", None)
    flash(f"Vous impersonnifiez {target.full_name()}.", "info")
    return redirect(url_for("auth.index"))


@bp.route("/stop-impersonation", methods=["POST"])
def stop_impersonation():
    original_id = session.pop("original_admin_id", None)
    if not original_id:
        return redirect(url_for("auth.index"))
    session["user_id"] = original_id
    g.pop("current_user", None)
    flash("Impersonnification terminée.", "success")
    return redirect(url_for("admin.admin_users"))


@bp.route("/users/<int:parent_id>/students", methods=["GET", "POST"])
@_admin_required
def admin_parent_students(parent_id: int):
    parent = _get_student_or_404(parent_id)
    if not parent.is_parent():
        flash("Cet utilisateur n'est pas un parent.", "warning")
        return redirect(url_for("admin.admin_users"))

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
        return redirect(url_for("admin.admin_users"))

    return render_template(
        "admin/parent_students.html",
        parent=parent,
        all_students=all_students,
    )


@bp.route("/users/new", methods=["GET", "POST"])
@_admin_required
def admin_create_user():
    cefr_levels, grade_levels, trimester_choices = _constants()

    def _render(form_data, selected_domains):
        return render_template(
            "admin/user_form.html",
            user=None,
            form_data=form_data,
            selected_domains=selected_domains,
            cefr_levels=cefr_levels,
            grade_levels=grade_levels,
            trimester_choices=trimester_choices,
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

        if target_cefr_level and target_cefr_level not in cefr_levels:
            flash("Le niveau CECRL est invalide.", "danger")
            return _render(form_data, selected_domains)

        if target_grade and target_grade not in grade_levels:
            flash("Le niveau scolaire est invalide.", "danger")
            return _render(form_data, selected_domains)

        target_trimester = None
        if target_trimester_raw:
            try:
                target_trimester = int(target_trimester_raw)
            except ValueError:
                flash("Le trimestre est invalide.", "danger")
                return _render(form_data, selected_domains)
            if target_trimester not in trimester_choices:
                flash("Le trimestre est invalide.", "danger")
                return _render(form_data, selected_domains)

        avatar_file = request.files.get("avatar")
        avatar_filename: Optional[str] = None
        if avatar_file and avatar_file.filename:
            if not _validate_image_file(avatar_file):
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
        return redirect(url_for("admin.admin_users"))

    return _render({}, [])


@bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@_admin_required
def admin_edit_user(user_id: int):
    target = _get_student_or_404(user_id)
    cefr_levels, grade_levels, trimester_choices = _constants()

    def _render(form_data, selected_domains):
        return render_template(
            "admin/user_form.html",
            user=target,
            form_data=form_data,
            selected_domains=selected_domains,
            cefr_levels=cefr_levels,
            grade_levels=grade_levels,
            trimester_choices=trimester_choices,
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

        if target_cefr_level and target_cefr_level not in cefr_levels:
            flash("Le niveau CECRL est invalide.", "danger")
            return _render(form_data, selected_domains)

        if target_grade and target_grade not in grade_levels:
            flash("Le niveau scolaire est invalide.", "danger")
            return _render(form_data, selected_domains)

        target_trimester = None
        if target_trimester_raw:
            try:
                target_trimester = int(target_trimester_raw)
            except ValueError:
                flash("Le trimestre est invalide.", "danger")
                return _render(form_data, selected_domains)
            if target_trimester not in trimester_choices:
                flash("Le trimestre est invalide.", "danger")
                return _render(form_data, selected_domains)

        avatar_file = request.files.get("avatar")
        new_avatar_filename: Optional[str] = None
        if avatar_file and avatar_file.filename:
            if not _validate_image_file(avatar_file):
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
        return redirect(url_for("admin.admin_users"))

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


@bp.route("/users/<int:user_id>/delete", methods=["GET", "POST"])
@_admin_required
def admin_delete_user(user_id: int):
    target = _get_student_or_404(user_id)

    if target.id == _current_user().id:
        flash("Vous ne pouvez pas supprimer votre propre compte.", "warning")
        return redirect(url_for("admin.admin_users"))

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
        return redirect(url_for("admin.admin_users"))

    session_count = len(target.sessions)
    badge_count = len(target.badges)
    return render_template(
        "admin/user_delete.html",
        target=target,
        session_count=session_count,
        badge_count=badge_count,
    )
