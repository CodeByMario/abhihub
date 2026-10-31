"""Focused tests for correlation IDs, metrics, and health probes."""

from app import app


def test_request_id_is_returned_and_metrics_are_recorded():
    app.config["TESTING"] = True
    client = app.test_client()

    response = client.get("/health/live", headers={"X-Request-ID": "test-request-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request-123"
    metrics_response = client.get("/metrics")
    assert b'http_requests_total' in metrics_response.data
    assert b'route="/health/live"' in metrics_response.data


def test_invalid_request_id_is_replaced():
    app.config["TESTING"] = True
    response = app.test_client().get("/health/live", headers={"X-Request-ID": "bad value"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"].startswith("req_")


def test_readiness_and_dependency_probes_are_non_sensitive():
    app.config["TESTING"] = True
    client = app.test_client()

    readiness = client.get("/health/ready")
    dependencies = client.get("/health/dependencies")

    assert readiness.status_code == 200
    assert readiness.get_json()["status"] == "ready"
    assert dependencies.status_code == 200
    assert "SUPABASE_KEY" not in dependencies.get_data(as_text=True)


def test_observability_rules_are_admin_protected():
    app.config["TESTING"] = True
    response = app.test_client().get("/api/admin/observability/rules")
    assert response.status_code in (302, 401, 403)


def test_observability_dashboard_is_admin_protected():
    app.config["TESTING"] = True
    response = app.test_client().get("/admin/observability")
    assert response.status_code in (302, 401, 403)
