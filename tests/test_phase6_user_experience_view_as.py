"""
tests/test_phase6_user_experience_view_as.py
Verification tests for Phase 6: User Experience, Diagnostics, and Read-Only View-As Sandbox.
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

from app import app, log_document_view
from services.admin_service import (
    start_view_as_session,
    stop_view_as_session,
    diagnose_document_access,
    get_user_experience_snapshot,
    mask_ip_address,
    log_user_activity,
    purge_old_user_activity_events
)
from methods.scoring_engine import process_event


@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        yield client


# ── 1. RBAC & Security: Moderator Cannot Start View-As ──

def test_moderator_cannot_start_view_as(client):
    """Moderator role must be rejected from initiating View-As sessions."""
    admin_user = {'uid': 'mod-1', 'email': 'mod@test.com', 'role': 'moderator'}
    ok, msg, view_as_data, sanitized = start_view_as_session(admin_user, 'student-1', 'Support ticket')
    assert ok is False
    assert "moderator" in msg.lower()


# ── 2. Security: Cannot Impersonate Admin, Superadmin, or Self ──

def test_cannot_impersonate_self_or_admin():
    """Admins cannot impersonate themselves or another admin/superadmin."""
    admin_user = {'uid': 'admin-1', 'email': 'admin@test.com', 'role': 'admin'}
    
    # Self-impersonation
    ok, msg, _, _ = start_view_as_session(admin_user, 'admin-1', 'Self check')
    assert ok is False
    assert "yourself" in msg.lower()

    # Empty reason
    ok, msg, _, _ = start_view_as_session(admin_user, 'student-1', '   ')
    assert ok is False
    assert "reason is required" in msg.lower()

    # Target is another admin
    mock_supabase = MagicMock()
    mock_supabase.table().select().eq().limit().execute.return_value = MagicMock(
        data=[{'id': 'admin-2', 'email': 'super@test.com', 'role': 'superadmin'}]
    )
    with patch('services.admin_service.init_supabase_admin', return_value=mock_supabase):
        ok, msg, _, _ = start_view_as_session(admin_user, 'admin-2', 'Valid reason')
        assert ok is False
        assert "cannot impersonate administrators" in msg.lower()


# ── 3. Central Sandbox: Non-GET Requests Blocked Centrally ──

def test_non_get_requests_blocked_during_view_as(client):
    """Central before_request hook must reject any non-GET request with 403."""
    now = datetime.now(timezone.utc)
    with client.session_transaction() as sess:
        sess['view_as'] = {
            'user_id': 'student-123',
            'user_name': 'Test Student',
            'admin_id': 'admin-1',
            'started_at': now.isoformat(),
            'expires_at': (now + timedelta(minutes=30)).isoformat(),
            'pages_visited': []
        }
        sess['user'] = {'uid': 'student-123', 'email': 'student@test.com', 'role': 'student'}

    # Attempt POST to a regular endpoint
    res = client.post('/api/search', json={'query': 'test'})
    assert res.status_code == 403
    data = res.get_json()
    assert "read-only mode active" in data.get('error', '').lower()

    # Attempt PUT
    res = client.put('/account/update', data={'student_name': 'Hacker'})
    assert res.status_code == 403


# ── 4. Central Sandbox: Sensitive Routes Return 403 ──

def test_sensitive_routes_blocked_in_view_as(client):
    """Payments, wallet, KYC, settings, and upload endpoints return 403."""
    now = datetime.now(timezone.utc)
    with client.session_transaction() as sess:
        sess['view_as'] = {
            'user_id': 'student-123',
            'user_name': 'Test Student',
            'admin_id': 'admin-1',
            'started_at': now.isoformat(),
            'expires_at': (now + timedelta(minutes=30)).isoformat(),
            'pages_visited': []
        }
        sess['user'] = {'uid': 'student-123', 'email': 'student@test.com', 'role': 'student'}

    sensitive_paths = [
        '/api/payments/manual-pending',
        '/api/wallet',
        '/api/kyc',
        '/api/upload',
        '/api/ai'
    ]
    for path in sensitive_paths:
        res = client.get(path)
        assert res.status_code == 403
        data = res.get_json()
        assert "forbidden in view-as mode" in data.get('error', '').lower()


# ── 5. Expiration: Session Expires After 30 Minutes ──

def test_view_as_session_expires(client):
    """A session beyond 30 minutes must be automatically terminated."""
    expired_time = datetime.now(timezone.utc) - timedelta(minutes=35)
    with client.session_transaction() as sess:
        sess['view_as'] = {
            'user_id': 'student-123',
            'user_name': 'Test Student',
            'admin_id': 'admin-1',
            'started_at': (expired_time - timedelta(minutes=30)).isoformat(),
            'expires_at': expired_time.isoformat(),
            'pages_visited': []
        }
        sess['admin_user_orig'] = {'uid': 'admin-1', 'email': 'admin@test.com', 'role': 'admin'}
        sess['user'] = {'uid': 'student-123', 'email': 'student@test.com', 'role': 'student'}

    # Next API request detects expiration
    res = client.get('/api/search')
    assert res.status_code == 403
    data = res.get_json()
    assert "expired" in data.get('error', '').lower()

    # Session is cleared
    with client.session_transaction() as sess:
        assert 'view_as' not in sess
        assert sess['user']['role'] == 'admin'


# ── 6. Audit Trail: Start and Stop Endpoints ──

def test_view_as_start_and_stop_flow(client):
    """Starting and stopping View-As writes audit logs and records visited pages."""
    mock_supabase = MagicMock()
    mock_supabase.table().select().eq().limit().execute.return_value = MagicMock(
        data=[{'id': 'std-99', 'student_name': 'Rohan Sharma', 'email': 'rohan@test.com', 'role': 'student'}]
    )

    with patch('services.admin_service.init_supabase_admin', return_value=mock_supabase), \
         patch('services.admin_service.record_audit_log') as mock_audit:

        # 1. Start View-As as admin
        with client.session_transaction() as sess:
            sess['user'] = {'uid': 'admin-1', 'email': 'admin@test.com', 'role': 'admin'}

        res = client.post('/api/admin/users/std-99/view-as/start', json={'reason': 'Customer ticket #123'})
        assert res.status_code == 200
        data = res.get_json()
        assert data['success'] is True
        assert mock_audit.called

        # 2. Stop View-As
        stop_res = client.post('/api/admin/view-as/stop')
        assert stop_res.status_code == 200
        assert stop_res.get_json()['success'] is True


# ── 7. Telemetry Suppression: Views and XP Not Incremented ──

def test_views_and_xp_suppressed_in_view_as(client):
    """Document view logging and scoring must be suppressed in View-As mode."""
    with client.session_transaction() as sess:
        sess['view_as'] = {'user_id': 'std-99', 'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()}
        sess['user'] = {'uid': 'std-99', 'email': 'std@test.com'}

    # Document view returns False (suppressed)
    with client.application.test_request_context():
        # within request context with view_as in session
        from flask import session
        session['view_as'] = {'user_id': 'std-99'}
        res = log_document_view('sample.pdf', 'https://example.com/sample.pdf', user_email='std@test.com')
        assert res is False

    # Scoring engine event scored is False
    with client.application.test_request_context():
        from flask import session
        session['view_as'] = {'user_id': 'std-99'}
        score_res = process_event('std-99', 'resource_viewed')
        assert score_res.get('scored') is False
        assert score_res.get('reason') == 'view_as mode'


# ── 8. IP Masking and Activity Purge ──

def test_ip_masking_and_activity_retention():
    """IPv4 and IPv6 addresses must be partially masked for privacy."""
    assert mask_ip_address('192.168.1.55') == '192.168.1.xxx'
    assert '127.0.0.xxx' in mask_ip_address('127.0.0.1')
    assert mask_ip_address('2001:0db8:85a3:0000:0000:8a2e:0370:7334') == '2001:0db8:85a3:*:*:*:*'

    # Retention purge helper executes delete with 90-day threshold
    mock_supabase = MagicMock()
    mock_supabase.table().delete().lt().execute.return_value = MagicMock(data=[{'id': '1'}])
    with patch('services.admin_service.init_supabase_admin', return_value=mock_supabase):
        count = purge_old_user_activity_events(days=90)
        assert count == 1
