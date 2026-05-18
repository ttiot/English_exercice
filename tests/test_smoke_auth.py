"""Smoke tests : authentification."""


def test_login_page_accessible(client):
    response = client.get("/login")
    assert response.status_code == 200


def test_login_with_valid_credentials_redirects_home(client, parent_user):
    response = client.post(
        "/login",
        data={"email": parent_user["email"], "password": parent_user["password"]},
    )
    assert response.status_code == 302
    assert response.headers["Location"].rstrip("/").endswith("")


def test_login_with_invalid_credentials_redirects_to_login(client, parent_user):
    response = client.post(
        "/login",
        data={"email": parent_user["email"], "password": "wrong-password"},
    )
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_protected_route_without_session_redirects_to_login(client):
    response = client.get("/parents/dashboard")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_logout_clears_session(client, parent_user):
    client.post(
        "/login",
        data={"email": parent_user["email"], "password": parent_user["password"]},
    )
    response = client.post("/logout")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

    # Après logout, une route protégée doit rediriger vers /login.
    response = client.get("/parents/dashboard")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
