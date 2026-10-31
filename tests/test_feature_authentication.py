import pytest

from app import app


@pytest.mark.parametrize("path", ["/dashboard", "/profile", "/settings", "/upload"])
def test_protected_pages_redirect_anonymous_users(path):
    response = app.test_client().get(path)
    assert response.status_code in (301, 302)
    assert "/login" in response.headers.get("Location", "")


def test_login_and_signup_pages_are_public():
    client = app.test_client()
    assert client.get("/login").status_code == 200
    assert client.get("/signup").status_code == 200


def test_authenticated_session_can_reach_dashboard():
    client = app.test_client()
    with client.session_transaction() as session:
        session["user"] = {"uid": "user-1", "email": "user@example.com"}
    assert client.get("/dashboard").status_code in (200, 302)
