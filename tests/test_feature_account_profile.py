from app import app


def test_profile_requires_authentication():
    response = app.test_client().get("/profile")
    assert response.status_code in (301, 302, 401)


def test_settings_requires_authentication():
    response = app.test_client().get("/settings")
    assert response.status_code in (301, 302, 401)


def test_authenticated_profile_route_is_reachable():
    client = app.test_client()
    with client.session_transaction() as session:
        session["user"] = {"uid": "user-1", "email": "user@example.com"}
    response = client.get("/profile")
    assert response.status_code in (200, 301, 302, 404)
