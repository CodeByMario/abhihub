from app import app


def test_admin_api_requires_authentication():
    response = app.test_client().get("/api/admin/users")
    assert response.status_code == 401


def test_student_cannot_access_admin_api():
    client = app.test_client()
    with client.session_transaction() as session:
        session["user"] = {"uid": "student-1", "email": "student@example.com", "role": "student"}
    response = client.get("/api/admin/users")
    assert response.status_code == 403


def test_admin_cannot_lock_themselves_out():
    client = app.test_client()
    admin_id = "00000000-0000-0000-0000-000000000099"
    with client.session_transaction() as session:
        session["user"] = {"uid": admin_id, "email": "admin@example.com", "role": "admin"}
    response = client.post(f"/api/admin/users/{admin_id}/block", json={"is_blocked": True})
    assert response.status_code == 403
