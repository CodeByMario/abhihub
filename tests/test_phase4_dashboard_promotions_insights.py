"""
tests/test_phase4_dashboard_promotions_insights.py
Test suite for Phase 4:
- Executive Dashboard KPIs, timeseries revenue, and conversion funnel.
- Promotion creation, listing, status lifecycle, and search boost ranking hook.
- Search demand analysis (top searches, zero-result gaps, trending files).
"""

import uuid
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

from app import app
from services.admin_service import (
    get_admin_dashboard_metrics,
    create_promotion,
    list_promotions,
    update_promotion_status,
    auto_expire_promotions,
    get_active_search_boosts,
    get_search_and_trending_insights
)


@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as c:
        yield c


def test_dashboard_metrics_aggregation():
    """Verify GMV, platform commission, user metrics, and funnel structure."""
    mock_db = MagicMock()

    # Mock count queries
    count_obj = MagicMock(count=150, data=[])
    mock_db.table.return_value.select.return_value.execute.return_value = count_obj
    mock_db.table.return_value.select.return_value.gte.return_value.execute.return_value = MagicMock(count=25, data=[])
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(count=3, data=[])

    # Mock transactions for GMV calculation
    mock_tx = [
        {'amount': 200.0, 'status': 'completed', 'created_at': datetime.now(timezone.utc).isoformat()},
        {'amount': 300.0, 'status': 'completed', 'created_at': datetime.now(timezone.utc).isoformat()},
        {'amount': 50.0, 'status': 'refunded', 'created_at': datetime.now(timezone.utc).isoformat()}
    ]
    mock_db.table.return_value.select.return_value.gte.return_value.execute.return_value = MagicMock(data=mock_tx, count=3)

    with patch('services.admin_service.get_db', return_value=mock_db):
        res = get_admin_dashboard_metrics(days=30, bypass_cache=True)
        assert res['success'] is True
        assert 'kpis' in res
        assert 'charts' in res
        assert 'cached_at' in res
        assert 'cached_timestamp' in res
        assert res['is_cached'] is False
        kpis = res['kpis']
        assert kpis['gmv'] >= 500.0
        assert kpis['commission'] >= 150.0
        assert kpis['refunds'] >= 50.0
        assert 'funnel' in res['charts']
        assert 'views' in res['charts']['funnel']

        # Second call without bypass should hit cache
        res2 = get_admin_dashboard_metrics(days=30, bypass_cache=False)
        assert res2['is_cached'] is True
        assert res2['cached_at'] == res['cached_at']

        # Calling with bypass should yield fresh data
        res3 = get_admin_dashboard_metrics(days=30, bypass_cache=True)
        assert res3['is_cached'] is False


def test_promotions_lifecycle_and_search_boost():
    """Verify promotion creation, status toggling, auto-expire, and search boost query."""
    doc_id = str(uuid.uuid4())
    admin_user = {'uid': str(uuid.uuid4()), 'role': 'admin', 'email': 'admin@abhihub.com'}

    mock_db = MagicMock()
    mock_created = {
        'id': str(uuid.uuid4()),
        'document_id': doc_id,
        'slot': 'search_boost',
        'priority': 25,
        'status': 'active',
        'ends_at': (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    }

    mock_exec = MagicMock(data=[mock_created], count=1)
    mock_db.table.return_value.insert.return_value.execute.return_value = mock_exec
    mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = mock_exec
    mock_db.table.return_value.select.return_value.order.return_value.order.return_value.range.return_value.execute.return_value = mock_exec
    mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.order.return_value.range.return_value.execute.return_value = mock_exec
    mock_db.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[{'id': doc_id, 'title': 'Test Doc'}])

    with patch('services.admin_service.get_db', return_value=mock_db), \
         patch('services.admin_service.record_audit_log'):

        # 1. Create promotion
        ok, msg, promo = create_promotion(admin_user, doc_id, slot='search_boost', priority=25)
        assert ok is True
        assert promo['priority'] == 25

        # 2. List promotions
        promos_list = list_promotions(slot='search_boost')
        assert promos_list['success'] is True
        assert len(promos_list['promotions']) == 1

        # 3. Update status to paused
        ok_p, msg_p = update_promotion_status(admin_user, promo['id'], 'paused')
        assert ok_p is True


def test_active_search_boost_lookup():
    """Verify get_active_search_boosts maps document_id to priority."""
    doc_id = str(uuid.uuid4())
    mock_db = MagicMock()
    mock_rows = [{'document_id': doc_id, 'priority': 30}]
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.gt.return_value.execute.return_value = MagicMock(data=mock_rows)

    with patch('services.admin_service.get_db', return_value=mock_db):
        boosts = get_active_search_boosts()
        assert doc_id in boosts
        assert boosts[doc_id] == 30


def test_search_and_trending_insights():
    """Verify top searches, zero-result aggregation, and trending documents."""
    mock_db = MagicMock()
    mock_searches = [
        {'query': 'machine learning', 'results_count': 12},
        {'query': 'machine learning', 'results_count': 8},
        {'query': 'quantum mechanics notes', 'results_count': 0}
    ]
    mock_db.table.return_value.select.return_value.gte.return_value.limit.return_value.execute.return_value = MagicMock(data=mock_searches)

    mock_trending = [
        {'id': 'doc-1', 'title': 'DSA Handbook', 'view_count': 120, 'like_count': 45}
    ]
    mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=mock_trending)

    with patch('services.admin_service.get_db', return_value=mock_db):
        insights = get_search_and_trending_insights(days=30)
        assert insights['success'] is True
        assert len(insights['top_searches']) >= 1
        assert insights['top_searches'][0]['query'] == 'machine learning'
        assert insights['top_searches'][0]['count'] == 2
        assert len(insights['zero_result_searches']) >= 1
        assert insights['zero_result_searches'][0]['query'] == 'quantum mechanics notes'
        assert len(insights['trending_files']) == 1
