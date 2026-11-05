from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from methods.scoring_engine import get_ad_decision


def _client_with_upload_count(upload_count):
    client = MagicMock()
    profile_query = MagicMock()
    profile_query.select.return_value = profile_query
    profile_query.eq.return_value = profile_query
    profile_query.limit.return_value.execute.return_value = SimpleNamespace(
        data=[{"paper_quota_remaining": 0}]
    )
    upload_query = MagicMock()
    upload_query.select.return_value = upload_query
    upload_query.eq.return_value = upload_query
    upload_query.limit.return_value.execute.return_value = SimpleNamespace(
        count=upload_count,
        data=[],
    )
    client.table.side_effect = lambda name: (
        profile_query if name == "profiles" else upload_query
    )
    return client


def test_consumers_receive_ads():
    with patch("methods.scoring_engine._get_client", return_value=_client_with_upload_count(0)):
        decision = get_ad_decision("user-1")

    assert decision["show_ads"] is True
    assert decision["density"] == "high"
    assert decision["verified_upload_count"] == 0


def test_verified_contributors_get_minimal_ads():
    with patch("methods.scoring_engine._get_client", return_value=_client_with_upload_count(1)):
        decision = get_ad_decision("user-1")

    assert decision["show_ads"] is True
    assert decision["density"] == "minimum"
    assert decision["verified_upload_count"] == 1


def test_active_contributors_are_ad_free():
    with patch("methods.scoring_engine._get_client", return_value=_client_with_upload_count(3)):
        decision = get_ad_decision("user-1")

    assert decision["show_ads"] is False
    assert decision["density"] == "off"
    assert decision["ad_free_contributor"] is True


def test_intrusive_ad_units_are_not_enabled():
    from pathlib import Path

    template = Path("templates/ads/third_party.html").read_text(encoding="utf-8")
    assert "abscloud.org/1/442567bc75eda61e014549835780ee0a" not in template
    assert "bauval.org/14/d343fa63fbc906d4cdbfde7220cba00" not in template


def test_non_content_routes_are_ad_free():
    from app import app, inject_ad_decision

    with app.test_request_context("/help"):
        with patch("methods.scoring_engine.get_ad_decision", return_value={
            "show_ads": True,
            "density": "high",
        }):
            context = inject_ad_decision()

    assert context["ads_allowed"] is False
    assert context["ad_density"] == "off"


def test_college_routes_can_show_content_ads():
    from app import app, inject_ad_decision

    with app.test_request_context("/college/ghrce"):
        with patch("methods.scoring_engine.get_ad_decision", return_value={
            "show_ads": True,
            "density": "minimum",
        }):
            context = inject_ad_decision()

    assert context["ads_allowed"] is True
    assert context["ad_density"] == "minimum"
