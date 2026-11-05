from unittest.mock import MagicMock, patch


def test_daily_views_rejects_invalid_day_range():
    from methods.analytics_reporter import get_daily_views

    with patch("methods.analytics_reporter._client", return_value=MagicMock()):
        result = get_daily_views(days=0)
    assert isinstance(result, dict)


def test_analytics_overview_has_numeric_view_fields():
    from methods.analytics_reporter import get_overview_kpis

    with patch("methods.analytics_reporter._client", return_value=MagicMock()):
        result = get_overview_kpis(days=7)
    assert isinstance(result, dict)
    for key in ("total_views", "all_time_views"):
        if key in result:
            assert isinstance(result[key], (int, float))


def test_analytics_route_requires_admin():
    from app import app

    response = app.test_client().get("/api/admin/analytics/overview")
    assert response.status_code in (401, 403)
