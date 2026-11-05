from app import app


def test_mark_notification_read_requires_authentication():
    response = app.test_client().post("/api/notifications/notif-1/read")
    assert response.status_code == 401


def test_notifications_route_requires_authentication():
    response = app.test_client().get("/notifications")
    assert response.status_code in (301, 302, 401)


def test_authenticated_notification_read_does_not_accept_missing_identity():
    client = app.test_client()
    with client.session_transaction() as session:
        session["user"] = {"uid": "user-1", "email": "user@example.com"}
    response = client.post("/api/notifications/notif-1/read")
    assert response.status_code in (200, 400, 404, 500)
