"""
tests/test_phase5_reviews_settings_security.py
Test suite for Phase 5:
- Reviews moderation (status update, deletion, fake review flag).
- Support ticket queue triage.
- Site settings read & toggle update.
- Immutable security audit logs listing.
"""

import uuid
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from app import app
from services.admin_service import (
    list_reviews,
    update_review_status,
    delete_review,
    list_support_tickets,
    update_ticket_status,
    get_site_settings,
    update_site_setting,
    list_audit_logs
)


@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as c:
        yield c


def test_reviews_moderation():
    """Verify listing, status modification, and deletion of reviews."""
    review_id = str(uuid.uuid4())
    admin_user = {'uid': str(uuid.uuid4()), 'role': 'admin', 'email': 'admin@abhihub.com'}

    mock_db = MagicMock()
    mock_review = {
        'id': review_id,
        'document_id': str(uuid.uuid4()),
        'user_id': str(uuid.uuid4()),
        'rating': 5,
        'review_text': 'Comprehensive handwritten notes!',
        'status': 'approved',
        'flagged_as_fake': False
    }

    mock_db.table.return_value.select.return_value.order.return_value.range.return_value.execute.return_value = MagicMock(data=[mock_review], count=1)
    mock_db.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
    mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_review])
    mock_db.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock()

    with patch('services.admin_service.get_db', return_value=mock_db), \
         patch('services.admin_service.record_audit_log') as mock_audit:

        # 1. List reviews
        res = list_reviews()
        assert res['success'] is True
        assert len(res['reviews']) == 1

        # 2. Update status to hidden
        ok_stat, msg_stat = update_review_status(admin_user, review_id, 'hidden', flagged_fake=True)
        assert ok_stat is True
        assert mock_audit.called

        # 3. Delete review
        ok_del, msg_del = delete_review(admin_user, review_id, reason="Spam comment")
        assert ok_del is True


def test_support_tickets_triage():
    """Verify support ticket triage and status resolution."""
    ticket_id = str(uuid.uuid4())
    admin_user = {'uid': str(uuid.uuid4()), 'role': 'admin', 'email': 'admin@abhihub.com'}

    mock_db = MagicMock()
    mock_ticket = {
        'id': ticket_id,
        'user_id': str(uuid.uuid4()),
        'subject': 'Unable to open CAE file',
        'status': 'open',
        'priority': 'urgent'
    }

    mock_db.table.return_value.select.return_value.order.return_value.range.return_value.execute.return_value = MagicMock(data=[mock_ticket], count=1)
    mock_db.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
    mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[mock_ticket])

    with patch('services.admin_service.get_db', return_value=mock_db), \
         patch('services.admin_service.record_audit_log') as mock_audit:

        # List tickets
        res = list_support_tickets()
        assert res['success'] is True
        assert len(res['tickets']) == 1

        # Resolve ticket
        ok, msg = update_ticket_status(admin_user, ticket_id, 'resolved', resolution_notes="Viewer refreshed")
        assert ok is True
        assert mock_audit.called


def test_site_settings_management():
    """Verify site configuration flag reading and updating."""
    admin_user = {'uid': str(uuid.uuid4()), 'role': 'superadmin', 'email': 'super@abhihub.com'}

    mock_db = MagicMock()
    mock_settings_rows = [
        {'key': 'maintenance_mode', 'value': False},
        {'key': 'payouts_enabled', 'value': True}
    ]
    mock_db.table.return_value.select.return_value.execute.return_value = MagicMock(data=mock_settings_rows)
    mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[{'key': 'maintenance_mode', 'value': True}])

    with patch('services.admin_service.get_db', return_value=mock_db), \
         patch('services.admin_service.record_audit_log'):

        settings = get_site_settings()
        assert settings['maintenance_mode'] is False
        assert settings['payouts_enabled'] is True

        ok, msg = update_site_setting(admin_user, 'maintenance_mode', True)
        assert ok is True


def test_audit_logs_query():
    """Verify admin audit log retrieval."""
    mock_db = MagicMock()
    mock_log = {
        'id': 'log-1',
        'admin_email': 'admin@abhihub.com',
        'action': 'verify_manual_payment',
        'target_type': 'payment',
        'target_id': 'ORD-123',
        'timestamp': datetime.now(timezone.utc).isoformat()
    }
    mock_db.table.return_value.select.return_value.order.return_value.range.return_value.execute.return_value = MagicMock(data=[mock_log], count=1)

    with patch('services.admin_service.get_db', return_value=mock_db):
        res = list_audit_logs()
        assert res['success'] is True
        assert len(res['logs']) == 1
        assert res['logs'][0]['action'] == 'verify_manual_payment'
