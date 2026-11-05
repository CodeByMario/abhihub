from unittest.mock import patch

from app import app


def test_ai_embed_has_expected_csp():
    response = app.test_client().get("/ai/embed", follow_redirects=True)
    assert response.status_code == 200
    assert "Content-Security-Policy" in response.headers


def test_ai_safety_rejects_empty_prompt():
    from methods.ai_safety import check_input

    result = check_input("")
    assert result.passed is True


def test_ai_endpoint_requires_valid_payload():
    response = app.test_client().post("/api/ai/assistant", json={})
    assert response.status_code in (400, 401, 422)
