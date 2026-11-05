"""
Unit and integration tests for AbhiHub Analytics Redesign.
Verifies zero-PII policies, input sanitization, rate limiting, and route contracts.
"""

import pytest
from flask import Flask, session
from methods.analytics_tracker import register_analytics_routes, get_full_profile_json


@pytest.fixture
def analytics_app():
    app = Flask(__name__)
    app.secret_key = "test-secret-key"
    register_analytics_routes(app)
    return app


@pytest.fixture
def client(analytics_app):
    return analytics_app.test_client()


def test_get_full_profile_json_has_no_pii(analytics_app):
    """Ensure user profile JSON embedded in templates exposes ZERO email/mobile/name fields."""
    with analytics_app.test_request_context():
        # Anonymous state
        profile = get_full_profile_json()
        assert "email" not in profile
        assert "mobile" not in profile
        assert "name" not in profile
        assert profile["userId"] == "anonymous"
        assert profile["isAuthenticated"] is False
        assert "creatorStatus" in profile
        assert "readerStatus" in profile
        assert "engagementStage" in profile


def test_get_full_profile_json_authenticated_no_pii(analytics_app):
    """Ensure authenticated state still excludes raw PII."""
    with analytics_app.test_request_context():
        session["user"] = {
            "uid": "123e4567-e89b-12d3-a456-426614174000",
            "email": "student@example.com",
            "name": "Secret Name",
            "provider": "google"
        }
        profile = get_full_profile_json()
        assert "email" not in profile
        assert "mobile" not in profile
        assert "name" not in profile
        assert profile["userId"] == "123e4567-e89b-12d3-a456-426614174000"
        assert profile["isAuthenticated"] is True


def test_analytics_pageview_endpoint(client):
    """Test /api/analytics/pageview accepts valid payloads."""
    payload = {
        "page_path": "/notes/dbms",
        "page_title": "DBMS Notes",
        "page_category": "notes",
        "session_id": "sess_123"
    }
    res = client.post("/api/analytics/pageview", json=payload)
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True


def test_analytics_user_properties_endpoint(client):
    """Test /api/analytics/user-properties returns zero-PII user properties."""
    res = client.get("/api/analytics/user-properties")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    props = data["userProperties"]
    assert "email" not in props
    assert "mobile" not in props


def test_analytics_error_endpoint(client):
    """Test /api/analytics/error logging."""
    payload = {
        "error_type": "PDF_RENDER_FAIL",
        "error_message": "Canvas render timeout",
        "severity": "warning",
        "page_path": "/preview/123"
    }
    res = client.post("/api/analytics/error", json=payload)
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True


def test_analytics_rate_limiting(client):
    """Test rate limiting prevents flooding."""
    payload = {"page_path": "/"}
    # Send 105 requests rapidly to trigger rate limiting (>100 req/min)
    rate_limited = False
    for _ in range(105):
        res = client.post("/api/analytics/pageview", json=payload)
        if res.status_code == 429:
            rate_limited = True
            break
    assert rate_limited is True
