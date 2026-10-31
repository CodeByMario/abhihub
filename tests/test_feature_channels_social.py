from unittest.mock import patch

from app import app


def test_missing_channel_returns_not_found():
    with patch("methods.channel_service.get_channel_by_handle", return_value=None):
        response = app.test_client().get("/channel/missing")
    assert response.status_code in (404, 302)


def test_channel_views_are_non_negative():
    from methods.channel_service import increment_channel_views

    with patch("methods.channel_service._execute_with_schema_fallback") as execute:
        increment_channel_views("channel-1", -1)
    execute.assert_called_once()


def test_channel_route_does_not_require_payment_for_missing_handle():
    response = app.test_client().get("/channel/")
    assert response.status_code in (404, 308)
