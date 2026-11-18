"""
tests/test_phase1_security_and_admin.py
Verification tests for:
1. Payment bypass security patch (Fake UTR does not grant document access).
2. Manual UTR status returns 'submitted' without immediate entitlement or wallet crediting.
3. Role-based access control (RBAC) on the manual payment queue (Moderator forbidden, Admin allowed).
4. Atomic fulfillment upon admin manual verification.
5. Mandatory rejection reason and idempotency on duplicate verification calls.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from app import app
from routes.api import has_document_access
from services.admin_service import role_rank, has_min_role, get_user_role
from services.admin_payment_service import (
    verify_manual_payment,
    reject_manual_payment,
    list_pending_manual_payments
)


@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        yield client


# ── 1. Security Gap Fix: Manual UTR must NOT unlock access or credit wallet ──

def test_manual_utr_submission_returns_submitted(client):
    """Submitting a manual UTR must record 'submitted' status and NOT 'completed'."""
    with client.session_transaction() as sess:
        sess['user'] = {'uid': 'student-uuid-999', 'email': 'student@example.com', 'role': 'student'}
        sess['purchased_documents'] = []

    with patch('routes.payments.init_supabase') as mock_sb, \
         patch('data.transactions.save_transaction_record') as mock_save:
        
        mock_client = MagicMock()
        mock_sb.return_value = mock_client
        
        resp = client.post('/api/payment/status', json={
            'order_id': 'order_fake_12345',
            'utr': '998877665544',
            'amount': '49.00',
            'doc_id': 'doc-secret-paid-101',
            'purpose': 'Document-doc-secret-paid-101'
        })

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['status'] == 'submitted'
        assert 'verification' in data['message'].lower()

        # Verify save_transaction_record was called with status 'submitted'
        mock_save.assert_called_once()
        args, kwargs = mock_save.call_args
        assert args[0] == 'order_fake_12345'
        assert args[1]['status'] == 'submitted'

    # Verify session was NOT granted access
    with client.session_transaction() as sess:
        assert 'doc-secret-paid-101' not in sess.get('purchased_documents', [])


def test_has_document_access_blocks_submitted_status():
    """Ensure has_document_access denies access when status is 'submitted'."""
    doc_id = 'test-doc-paid-001'
    user_id = 'buyer-uuid-111'
    doc_data = {
        'id': doc_id,
        'title': 'Paid Gate Notes',
        'is_paid': True,
        'price': 99.0,
        'uploader_id': 'seller-uuid-222',
        'uploader_email': 'seller@example.com'
    }

    with patch('methods.supabase_helper.get_document_by_id_rich', return_value={'success': True, 'data': doc_data}), \
         patch('methods.supabase_helper.init_supabase') as mock_sb:

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.data = [{'id': 'tx-1', 'status': 'submitted', 'admin_notes': f'doc_id={doc_id}'}]
        mock_client.table().select().eq().ilike().execute.return_value = mock_res
        mock_sb.return_value = mock_client

        with app.test_request_context():
            from flask import session
            session['user'] = {'uid': user_id, 'email': 'buyer@example.com', 'role': 'student'}
            
            # Must return False because status is 'submitted', not 'completed'
            assert has_document_access(user_id, doc_id, document=doc_data) is False


def test_has_document_access_allows_completed_status():
    """Ensure has_document_access grants access only when status is 'completed'."""
    doc_id = 'test-doc-paid-002'
    user_id = 'buyer-uuid-112'
    doc_data = {
        'id': doc_id,
        'title': 'Paid Gate Notes 2',
        'is_paid': True,
        'price': 49.0,
        'uploader_id': 'seller-uuid-222',
        'uploader_email': 'seller@example.com'
    }

    with patch('methods.supabase_helper.get_document_by_id_rich', return_value={'success': True, 'data': doc_data}), \
         patch('methods.supabase_helper.init_supabase') as mock_sb:

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.data = [{'id': 'tx-2', 'status': 'completed', 'admin_notes': f'doc_id={doc_id}'}]
        mock_client.table().select().eq().ilike().execute.return_value = mock_res
        mock_sb.return_value = mock_client

        with app.test_request_context():
            from flask import session
            session['user'] = {'uid': user_id, 'email': 'buyer@example.com', 'role': 'student'}
            
            assert has_document_access(user_id, doc_id, document=doc_data) is True


# ── 2. RBAC Permissions on Manual Verification Queue ──

def test_manual_queue_rbac_moderator_forbidden(client):
    """Moderator role (20) must be forbidden from accessing payment verification endpoints."""
    with client.session_transaction() as sess:
        sess['user'] = {'uid': 'mod-uuid-1', 'email': 'mod@abhihub.com', 'role': 'moderator'}

    # Queue list requires admin (30)
    resp = client.get('/api/admin/payment/manual-pending')
    assert resp.status_code == 403

    # Verification requires admin (30)
    resp = client.post('/api/admin/payment/manual-verify', json={'order_id': 'order_123'})
    assert resp.status_code == 403

    # Rejection requires admin (30)
    resp = client.post('/api/admin/payment/manual-reject', json={'order_id': 'order_123', 'reason': 'Fake'})
    assert resp.status_code == 403


def test_manual_queue_rbac_admin_allowed(client):
    """Admin role (30) and Superadmin (40) must be allowed to access manual queue."""
    with client.session_transaction() as sess:
        sess['user'] = {'uid': 'admin-uuid-1', 'email': 'admin@abhihub.com', 'role': 'admin'}

    with patch('services.admin_payment_service.get_db') as mock_db:
        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.data = []
        mock_res.count = 0
        mock_client.table().select().eq().order().range().execute.return_value = mock_res
        mock_db.return_value = mock_client

        resp = client.get('/api/admin/payment/manual-pending')
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True


# ── 3. Atomic Verification & Rejection Logic ──

def test_verify_manual_payment_fulfillment():
    """Verify manual payment updates status to completed, credits creator, and sends notification."""
    admin_user = {'uid': 'admin-uuid-1', 'email': 'admin@test.com', 'role': 'admin'}
    order_id = 'order_valid_999'
    doc_id = 'doc_abc_123'
    buyer_id = 'buyer-uuid-555'

    mock_tx = {
        'id': 'tx-uuid-1',
        'order_id': order_id,
        'status': 'submitted',
        'user_id': buyer_id,
        'amount': 75.0,
        'admin_notes': f'doc_id={doc_id}',
        'utr': '112233445566'
    }

    with patch('services.admin_payment_service.get_db') as mock_db, \
         patch('methods.wallet_service.credit_creator_for_purchase') as mock_credit, \
         patch('services.admin_payment_service.log_notification') as mock_notif, \
         patch('services.admin_payment_service.record_audit_log') as mock_audit:

        mock_client = MagicMock()
        mock_query_res = MagicMock()
        mock_query_res.data = [mock_tx]
        mock_client.table().select().eq().limit().execute.return_value = mock_query_res
        mock_db.return_value = mock_client

        ok, msg, res = verify_manual_payment(order_id, admin_user, notes='Verified via bank statement')

        assert ok is True
        assert "verified and fulfilled" in msg
        mock_credit.assert_called_once_with(order_id, doc_id, 75.0)
        mock_notif.assert_called_once()
        mock_audit.assert_called_once()


def test_verify_manual_payment_idempotency():
    """Calling verify on an already completed transaction should succeed without double-fulfillment."""
    admin_user = {'uid': 'admin-uuid-1', 'email': 'admin@test.com', 'role': 'admin'}
    order_id = 'order_already_done'

    mock_tx = {
        'id': 'tx-uuid-2',
        'order_id': order_id,
        'status': 'completed',
        'amount': 50.0
    }

    with patch('services.admin_payment_service.get_db') as mock_db, \
         patch('methods.wallet_service.credit_creator_for_purchase') as mock_credit:

        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.data = [mock_tx]
        mock_client.table().select().eq().limit().execute.return_value = mock_res
        mock_db.return_value = mock_client

        ok, msg, res = verify_manual_payment(order_id, admin_user)

        assert ok is True
        assert "already verified" in msg
        mock_credit.assert_not_called()


def test_reject_manual_payment_requires_reason():
    """Rejecting a payment requires a non-empty reason."""
    admin_user = {'uid': 'admin-uuid-1', 'email': 'admin@test.com', 'role': 'admin'}
    ok, msg = reject_manual_payment('order_123', admin_user, reason='   ')
    assert ok is False
    assert "reason is strictly required" in msg


# ── 4. Webhook & Commission Idempotency Verification ──

def test_razorpay_webhook_sets_status_completed(client):
    """Confirm Razorpay webhook path marks order status as 'completed'."""
    from routes.webhooks import fulfill_order_transaction
    order_id = 'order_rzp_webhook_123'
    
    with patch('data.transactions.save_transaction_record') as mock_save, \
         patch('methods.payment_engine.engine.credit_creator') as mock_credit:
        
        ok = fulfill_order_transaction(order_id, 100.0, doc_id='doc-webhook-1', user_id='buyer-uuid-777', source='razorpay_webhook')
        assert ok is True
        mock_save.assert_called_once()
        args, kwargs = mock_save.call_args
        assert args[0] == order_id
        assert args[1]['status'] == 'completed'
        assert 'verified_via=razorpay_webhook' in args[1]['admin_notes']


def test_manual_verify_applies_commission_and_is_idempotent():
    """Confirm manual verify applies canonical commission split via credit_creator_for_purchase and is idempotent."""
    admin_user = {'uid': 'admin-uuid-1', 'email': 'admin@test.com', 'role': 'admin'}
    order_id = 'order_commission_check'
    doc_id = 'doc_comm_1'
    
    mock_tx = {
        'id': 'tx-comm-uuid',
        'order_id': order_id,
        'status': 'submitted',
        'user_id': 'buyer-999',
        'amount': 100.0,
        'admin_notes': f'doc_id={doc_id}',
        'utr': '112233445566'
    }

    with patch('services.admin_payment_service.get_db') as mock_db, \
         patch('methods.wallet_service.credit_creator_for_purchase') as mock_credit, \
         patch('services.admin_payment_service.log_notification'), \
         patch('services.admin_payment_service.record_audit_log'):

        mock_client = MagicMock()
        mock_query_res = MagicMock()
        mock_query_res.data = [mock_tx]
        mock_client.table().select().eq().limit().execute.return_value = mock_query_res
        mock_db.return_value = mock_client

        # First verification
        ok1, msg1, res1 = verify_manual_payment(order_id, admin_user)
        assert ok1 is True
        assert res1['status'] == 'completed'
        mock_credit.assert_called_once_with(order_id, doc_id, 100.0)

        # Second verification (immediate repeat click)
        mock_tx['status'] = 'completed'
        ok2, msg2, res2 = verify_manual_payment(order_id, admin_user)
        assert ok2 is True
        assert "already verified" in msg2
        # credit_creator_for_purchase must NOT be called a second time
        assert mock_credit.call_count == 1

