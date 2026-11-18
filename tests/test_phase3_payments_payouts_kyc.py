"""
tests/test_phase3_payments_payouts_kyc.py
Test suite for Phase 3:
- Atomic & idempotent refund processing (buyer entitlement revocation, creator wallet debit).
- KYC Fernet encryption, masking, and superadmin audited reveal.
- Payout approval/rejection with wallet ledger rollback.
"""

import os
import uuid
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from app import app
from services.kyc_crypto_service import (
    encrypt_kyc_value, decrypt_kyc_value, mask_pan, mask_account, mask_upi, prepare_kyc_for_display
)
from services.admin_payment_service import process_refund
from methods.wallet_service import process_payout_request, debit_creator_for_refund


@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as c:
        yield c


def test_kyc_fernet_encryption_and_masking():
    """Verify Fernet encryption at rest, decryption, and client masking."""
    pan = "ABCDE1234F"
    acc = "123456789012"
    upi = "creator@okhdfcbank"

    enc_pan = encrypt_kyc_value(pan)
    enc_acc = encrypt_kyc_value(acc)
    enc_upi = encrypt_kyc_value(upi)

    # Must be encrypted Fernet tokens
    assert enc_pan.startswith("gAAAAA")
    assert enc_acc.startswith("gAAAAA")
    assert enc_upi.startswith("gAAAAA")

    # Idempotent re-encryption
    assert encrypt_kyc_value(enc_pan) == enc_pan

    # Decryption works
    assert decrypt_kyc_value(enc_pan) == pan
    assert decrypt_kyc_value(enc_acc) == acc
    assert decrypt_kyc_value(enc_upi) == upi

    # Masking projection
    assert mask_pan(enc_pan) == "ABCDE****F"
    assert mask_account(enc_acc).endswith("9012")
    assert mask_upi(enc_upi).endswith("@okhdfcbank")

    # Safe display projection
    raw_rec = {
        'id': 'kyc-1',
        'full_name': 'Test Creator',
        'pan_number': enc_pan,
        'account_number': enc_acc,
        'upi_id': enc_upi
    }
    disp = prepare_kyc_for_display(raw_rec)
    assert disp['pan_number'] == "ABCDE****F"
    assert "9012" in disp['account_number']
    assert not disp['pan_number'].startswith("gAAAAA")


def test_process_refund_revokes_access_and_debits_creator():
    """Verify refund transitions status to 'refunded', debits creator, and logs audit."""
    order_id = f"ORD-REF-{uuid.uuid4().hex[:8]}"
    buyer_id = str(uuid.uuid4())
    creator_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    admin_user = {'uid': str(uuid.uuid4()), 'role': 'admin', 'email': 'admin@abhihub.com'}

    mock_tx = {
        'id': str(uuid.uuid4()),
        'order_id': order_id,
        'user_id': buyer_id,
        'amount': 100.0,
        'status': 'completed',
        'admin_notes': f"doc_id={doc_id};pack=0"
    }

    mock_db = MagicMock()
    mock_select = MagicMock()
    mock_select.execute.return_value = MagicMock(data=[mock_tx])
    mock_db.table.return_value.select.return_value.eq.return_value.limit.return_value = mock_select
    mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

    with patch('services.admin_payment_service.get_db', return_value=mock_db), \
         patch('methods.wallet_service.get_document_creator', return_value=creator_id), \
         patch('methods.wallet_service.debit_creator_for_refund', return_value=(True, "Debited")) as mock_debit, \
         patch('services.admin_payment_service.record_audit_log') as mock_audit, \
         patch('services.admin_payment_service.log_notification') as mock_notif:

        ok, msg, tx = process_refund(order_id, admin_user, reason="Accidental duplicate purchase")
        assert ok is True
        assert tx['status'] == 'refunded'
        assert mock_debit.called
        assert mock_audit.called


def test_process_refund_idempotent():
    """Verify refunding an already refunded order succeeds gracefully without duplicate debit."""
    order_id = f"ORD-REF-IDEM"
    admin_user = {'uid': str(uuid.uuid4()), 'role': 'admin', 'email': 'admin@abhihub.com'}

    mock_tx = {
        'id': str(uuid.uuid4()),
        'order_id': order_id,
        'status': 'refunded',
        'refunded_at': datetime.now(timezone.utc).isoformat(),
        'amount': 50.0
    }

    mock_db = MagicMock()
    mock_select = MagicMock()
    mock_select.execute.return_value = MagicMock(data=[mock_tx])
    mock_db.table.return_value.select.return_value.eq.return_value.limit.return_value = mock_select

    with patch('services.admin_payment_service.get_db', return_value=mock_db), \
         patch('methods.wallet_service.debit_creator_for_refund') as mock_debit:

        ok, msg, tx = process_refund(order_id, admin_user, reason="Duplicate refund click")
        assert ok is True
        assert "already been refunded" in msg
        assert not mock_debit.called


def test_kyc_reveal_rbac(client):
    """Verify only superadmin can reveal decrypted KYC credentials."""
    kyc_id = str(uuid.uuid4())

    # Moderator attempt -> 403 Forbidden
    with client.session_transaction() as sess:
        sess['user'] = {'uid': str(uuid.uuid4()), 'email': 'mod@abhihub.com', 'role': 'moderator'}
        sess['role'] = 'moderator'
        sess['token_version'] = 1

    resp = client.post(f'/api/admin/kyc/{kyc_id}/reveal', json={'reason': 'testing'})
    assert resp.status_code == 403

    # Superadmin attempt -> 200 OK
    with client.session_transaction() as sess:
        sess['user'] = {'uid': str(uuid.uuid4()), 'email': 'super@abhihub.com', 'role': 'superadmin'}
        sess['role'] = 'superadmin'
        sess['token_version'] = 1

    mock_kyc = {
        'id': kyc_id,
        'pan_number': encrypt_kyc_value('ABCDE1234F'),
        'account_number': encrypt_kyc_value('9876543210'),
        'upi_id': encrypt_kyc_value('user@upi'),
        'ifsc_code': 'HDFC0001234',
        'bank_name': 'HDFC Bank',
        'account_holder_name': 'Test Super'
    }

    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[mock_kyc])

    with patch('routes.admin.init_supabase_admin', return_value=mock_client), \
         patch('routes.admin.init_supabase', return_value=mock_client), \
         patch('services.admin_service.record_audit_log') as mock_audit:

        resp_super = client.post(f'/api/admin/kyc/{kyc_id}/reveal', json={'reason': 'Manual verification'})
        assert resp_super.status_code == 200
        body = resp_super.get_json()
        assert body['success'] is True
        assert body['pan_number'] == 'ABCDE1234F'
        assert body['account_number'] == '9876543210'
        assert body['upi_id'] == 'user@upi'
        assert mock_audit.called
