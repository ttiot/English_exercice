"""Smoke tests : parcours élève / parent (dashboard, accès admin)."""


def test_parent_dashboard_accessible_to_parent(client, parent_user):
    client.post(
        "/login",
        data={"email": parent_user["email"], "password": parent_user["password"]},
    )
    response = client.get("/parents/dashboard")
    assert response.status_code == 200


def test_parent_dashboard_forbidden_to_student(client, student_user):
    client.post(
        "/login",
        data={"email": student_user["email"], "password": student_user["password"]},
    )
    response = client.get("/parents/dashboard")
    # _parent_required redirige (302) ou abort(403) selon l'implémentation.
    assert response.status_code in (302, 403)


def test_admin_users_accessible_to_admin(client, admin_user):
    client.post(
        "/login",
        data={"email": admin_user["email"], "password": admin_user["password"]},
    )
    response = client.get("/admin/users")
    assert response.status_code == 200


def test_admin_users_forbidden_to_parent(client, parent_user):
    client.post(
        "/login",
        data={"email": parent_user["email"], "password": parent_user["password"]},
    )
    response = client.get("/admin/users")
    assert response.status_code in (302, 403)


def test_admin_openai_config_accessible_to_admin(client, admin_user):
    client.post(
        "/login",
        data={"email": admin_user["email"], "password": admin_user["password"]},
    )
    response = client.get("/admin/openai/config")
    assert response.status_code == 200


def test_health_endpoint_after_login(client, admin_user):
    # NB : `/health` est actuellement intercepté par `require_login()` car il
    # n'est pas dans la liste blanche (`main.login`/`main.register`/`main.logout`).
    # Le smoke test se contente donc de vérifier qu'il répond 200 une fois
    # authentifié — le comportement public éventuel est un bug à traiter hors
    # refactor structurel.
    client.post(
        "/login",
        data={"email": admin_user["email"], "password": admin_user["password"]},
    )
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
