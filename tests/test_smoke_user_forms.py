"""Smoke tests : parcours form utilisateur (création + édition + password).

Ces tests valident que la factorisation vers ``services/user_form_handler.py``
n'a pas changé le comportement sur les 3 entry points qui partagent la logique
de validation.
"""


def _login(client, email: str, password: str):
    return client.post(
        "/login", data={"email": email, "password": password}, follow_redirects=False
    )


def test_admin_creates_a_parent_account(app, client, admin_user):
    """Admin crée un compte parent via /admin/users/new (role libre)."""
    _login(client, admin_user["email"], admin_user["password"])

    response = client.post(
        "/admin/users/new",
        data={
            "first_name": "Nora",
            "email": "nora.parent@test.local",
            "role": "parent",
            "password": "ParentPass123!",
            "password_confirm": "ParentPass123!",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/admin/users" in response.headers["Location"]

    with app.app_context():
        from app.models import Student
        created = Student.query.filter_by(email="nora.parent@test.local").first()
        assert created is not None
        assert created.role == "parent"


def test_parent_edits_managed_student_profile(app, client, parent_user):
    """Un parent crée un élève puis modifie son profil via /students/<id>/settings."""
    _login(client, parent_user["email"], parent_user["password"])

    # Créer l'élève
    client.post(
        "/students/new",
        data={
            "first_name": "Eva",
            "email": "eva.kid@test.local",
            "password": "KidPassWord123!",
            "password_confirm": "KidPassWord123!",
        },
    )
    with app.app_context():
        from app.models import Student
        student = Student.query.filter_by(email="eva.kid@test.local").first()
        assert student is not None
        student_id = student.id

    # Éditer son profil
    response = client.post(
        f"/students/{student_id}/settings",
        data={
            "action": "profile",
            "first_name": "Eva-Marie",
            "email": "eva.kid@test.local",
            "age": "11",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        from app.models import Student
        updated = Student.query.get(student_id)
        assert updated.first_name == "Eva-Marie"
        assert updated.age == 11


def test_student_changes_own_password(app, client, student_user):
    """L'élève change son propre mot de passe avec son ancien."""
    _login(client, student_user["email"], student_user["password"])

    response = client.post(
        f"/students/{student_user['id']}/settings",
        data={
            "action": "password",
            "current_password": student_user["password"],
            "new_password": "NewSecret2024!",
            "confirm_password": "NewSecret2024!",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/settings" in response.headers["Location"]

    # Le nouveau mdp doit fonctionner
    client.post("/logout")
    login_resp = _login(client, student_user["email"], "NewSecret2024!")
    assert login_resp.status_code == 302
    assert "/login" not in login_resp.headers["Location"]
