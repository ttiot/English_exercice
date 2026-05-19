"""Routes ``/admin/users/*`` : gestion des comptes (rôles, impersonation, CRUD).
"""

from flask import (
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

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
from ...services.curriculum import DOMAIN_CHOICES, _domain_list
from ...services.user_form_handler import (
    UserFormError,
    create_user_from_form,
    update_user_from_form,
)
from . import bp


def _constants():
    from ...routes import CEFR_LEVELS, GRADE_LEVELS, TRIMESTER_CHOICES

    return CEFR_LEVELS, GRADE_LEVELS, TRIMESTER_CHOICES


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
        try:
            new_user = create_user_from_form(
                request.form,
                request.files,
                role_choice_allowed=True,
                default_role="student",
                cefr_levels=cefr_levels,
                grade_levels=grade_levels,
                trimester_choices=trimester_choices,
            )
        except UserFormError as exc:
            flash(exc.message, "danger")
            return _render(exc.form_data, exc.selected_domains)
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
        try:
            update_user_from_form(
                target,
                request.form,
                request.files,
                role_choice_allowed=True,
                current_user=_current_user(),
                cefr_levels=cefr_levels,
                grade_levels=grade_levels,
                trimester_choices=trimester_choices,
                accept_inline_password=True,
            )
        except UserFormError as exc:
            flash(exc.message, "danger")
            return _render(exc.form_data, exc.selected_domains)
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
