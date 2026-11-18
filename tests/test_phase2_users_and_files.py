"""
tests/test_phase2_users_and_files.py
Unit and integration tests for Phase 2:
1. User moderation (temp block, permanent ban, auto-unblock via APScheduler).
2. Forced session revocation & token_version validation in auth_required.
3. Formal user warning and admin internal notes.
4. Wallet adjustments with mandatory reason and ledger tracking.
5. Duplicate explorer clustering and resolution.
6. Anti-lockout safeguards on moderation actions.
"""

import time
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

from app import app
from services.admin_service import (
    set_user_block,
    set_user_ban,
    force_logout_user,
    warn_user,
    add_admin_note,
    get_admin_notes,
    adjust_user_wallet,
    auto_unblock_expired_users,
    find_duplicate_files,
    resolve_duplicate_group,
    get_user_token_version,
    check_anti_lockout
)


@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        yield client


# ── 1. Temp Block & Force Logout Session Invalidation ──

def test_temp_block_increments_token_version():
    """Blocking a user must update token_version so active sessions are revoked."""
    admin_user = {'uid': 'admin-uuid-1', 'email': 'admin@test.com', 'role': 'admin'}
    target_uid = 'student-uuid-444'

    with patch('services.admin_service.get_db') as mock_db, \
         patch('services.admin_service.get_user_token_version', return_value=1), \
         patch('services.admin_service.record_audit_log'), \
         patch('services.admin_service.log_notification'):

        mock_client = MagicMock()
        mock_client.table().update().eq().execute.return_value = MagicMock(data=[{'id': target_uid}])
        mock_db.return_value = mock_client

        ok, msg = set_user_block(admin_user, target_uid, is_blocked=True, reason="Spamming", expiry_days=7)
        assert ok is True

        # Verify update payload included token_version = 2 and blocked_until
        update_call = mock_client.table().update.call_args[0][0]
        assert update_call['is_blocked'] is True
        assert update_call['token_version'] == 2
        assert update_call['blocked_until'] is not None


def test_auth_required_rejects_revoked_token_version(client):
    """A user whose session has an older token_version must be logged out."""
    with client.session_transaction() as sess:
        sess['user'] = {'uid': 'user-revoked-1', 'email': 'user@test.com', 'role': 'student'}
        sess['token_version'] = 1  # Older session version

    # DB returns newer token_version (e.g. 2, after force logout or block)
    with patch('services.admin_service.get_user_token_version', return_value=2):
        resp = client.post('/api/payment/status', json={'order_id': 'test', 'utr': '123456789012'})
        # auth_required triggers 401
        assert resp.status_code == 401
        assert "Session expired or revoked" in resp.get_json()['message']

    # Verify session was cleared
    with client.session_transaction() as sess:
        assert 'user' not in sess


# ── 2. APScheduler Auto-Unblock Job ──

def test_auto_unblock_expired_users():
    """auto_unblock_expired_users must find users whose blocked_until <= now and unblock them."""
    expired_user = {
        'id': 'user-exp-1',
        'email': 'exp@test.com',
        'blocked_until': (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    }

    with patch('services.admin_service.get_db') as mock_db, \
         patch('services.admin_service.record_audit_log') as mock_audit, \
         patch('services.admin_service.log_notification'):

        mock_client = MagicMock()
        mock_query_res = MagicMock()
        mock_query_res.data = [expired_user]
        mock_client.table().select().eq().lte().execute.return_value = mock_query_res
        mock_db.return_value = mock_client

        unblocked_count = auto_unblock_expired_users()
        assert unblocked_count == 1
        mock_client.table().update.assert_called_with({
            'is_blocked': False,
            'blocked_until': None,
            'blocked_reason': None,
            'block_reason': None,
            'updated_at': mock_client.table().update.call_args[0][0]['updated_at']
        })
        mock_audit.assert_called_once()


# ── 3. Force Logout & Warn User ──

def test_force_logout_user():
    """force_logout_user increments token_version and logs audit entry."""
    admin_user = {'uid': 'admin-uuid-1', 'email': 'admin@test.com', 'role': 'admin'}
    target_uid = 'student-uuid-555'

    with patch('services.admin_service.get_db') as mock_db, \
         patch('services.admin_service.get_user_token_version', return_value=3), \
         patch('services.admin_service.record_audit_log') as mock_audit:

        mock_client = MagicMock()
        mock_db.return_value = mock_client

        ok, msg = force_logout_user(admin_user, target_uid)
        assert ok is True
        mock_client.table().update.assert_called_with({
            'token_version': 4,
            'updated_at': mock_client.table().update.call_args[0][0]['updated_at']
        })
        mock_audit.assert_called_once()


def test_warn_user():
    """warn_user creates an admin note and notifies user."""
    admin_user = {'uid': 'admin-uuid-1', 'email': 'admin@test.com', 'role': 'admin'}
    target_uid = 'student-uuid-666'

    with patch('services.admin_service.get_db') as mock_db, \
         patch('services.admin_service.log_notification') as mock_notif, \
         patch('services.admin_service.record_audit_log') as mock_audit:

        mock_client = MagicMock()
        mock_db.return_value = mock_client

        ok, msg = warn_user(admin_user, target_uid, "Suspicious upload activity")
        assert ok is True
        mock_notif.assert_called_once()
        mock_audit.assert_called_once()


# ── 4. Wallet Adjustment (Admin Required & Ledger Entry) ──

def test_adjust_user_wallet_rbac():
    """Moderator cannot adjust wallet; Admin can adjust wallet."""
    mod_user = {'uid': 'mod-uuid-1', 'email': 'mod@test.com', 'role': 'moderator'}
    admin_user = {'uid': 'admin-uuid-1', 'email': 'admin@test.com', 'role': 'admin'}
    target_uid = 'creator-uuid-777'

    # Moderator denied
    ok, msg = adjust_user_wallet(mod_user, target_uid, 50.0, "Bonus")
    assert ok is False
    assert "Permission Denied" in msg

    # Admin allowed
    with patch('services.admin_service.get_db') as mock_db, \
         patch('services.admin_service.record_audit_log') as mock_audit:

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.data = [{'current_balance': 100.0}]
        mock_client.table().select().eq().limit().execute.return_value = mock_res
        mock_db.return_value = mock_client

        ok, msg = adjust_user_wallet(admin_user, target_uid, 50.0, "Contest prize")
        assert ok is True
        assert "50" in msg
        mock_audit.assert_called_once()


# ── 5. Duplicate Explorer & Cluster Resolution ──

def test_find_and_resolve_duplicates():
    """find_duplicate_files detects matching hashes; resolve_duplicate_group cleans duplicates."""
    admin_user = {'uid': 'admin-uuid-1', 'email': 'admin@test.com', 'role': 'admin'}

    sample_docs = [
        {'id': 'doc-1', 'title': 'Physics Notes 1', 'file_hash': 'abcdef1234567890abcdef', 'view_count': 100},
        {'id': 'doc-2', 'title': 'Physics Notes Duplicate', 'file_hash': 'abcdef1234567890abcdef', 'view_count': 5},
    ]

    with patch('services.admin_service.get_db') as mock_db:
        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.data = sample_docs
        mock_client.table().select().order().limit().execute.return_value = mock_res
        mock_db.return_value = mock_client

        groups = find_duplicate_files()
        assert len(groups) == 1
        assert groups[0]['count'] == 2

    # Resolve cluster
    with patch('services.admin_service.get_db') as mock_db, \
         patch('services.admin_service.record_audit_log') as mock_audit:

        mock_client = MagicMock()
        mock_db.return_value = mock_client

        ok, msg = resolve_duplicate_group(admin_user, keep_doc_id='doc-1', remove_doc_ids=['doc-2'], reason='Exact duplicate')
        assert ok is True
        assert "Kept primary" in msg
        mock_audit.assert_called_once()
