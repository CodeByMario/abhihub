from unittest.mock import MagicMock, patch

from methods.payment_engine import PaymentEngine


def test_credit_views_rejects_invalid_amounts():
    engine = PaymentEngine()
    assert engine.credit_views("", 1, "test") is False
    assert engine.credit_views("user-1", 0, "test") is False
    assert engine.credit_views("user-1", -1, "test") is False


def test_credit_views_updates_balance_and_ledger():
    engine = PaymentEngine()
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"paper_quota_remaining": 3, "email": "user@example.com"}
    ]
    with patch("methods.payment_engine._db", return_value=db), \
         patch.object(engine, "_ledger_credit"), \
         patch.object(engine, "_invalidate_quota_cache"):
        assert engine.credit_views("user-1", 2, "test_reward")
    db.table.return_value.update.assert_called_with({"paper_quota_remaining": 5})


def test_credit_packs_endpoint_is_publicly_shaped():
    from app import app

    response = app.test_client().get("/api/credit-packs")
    assert response.status_code in (200, 401, 403)


def test_paid_view_pack_credits_balance_when_supabase_insert_is_unavailable():
    from app import app

    client = app.test_client()
    with client.session_transaction() as session:
        session["user"] = {"uid": "user-1", "email": "user@example.com"}

    engine = MagicMock()
    engine.credit_views.return_value = True
    engine.get_view_balance.return_value = 27
    with patch("routes.payments.init_supabase", return_value=None), \
         patch("data.transactions.is_order_completed", return_value=False), \
         patch("data.transactions.save_transaction_record"), \
         patch("methods.payment_engine.engine", engine):
        response = client.post(
            "/api/payment/status",
            json={
                "order_id": "order-pack-1",
                "utr": "123456789012",
                "amount": "50",
                "purpose": "Credits-25-pack=25",
            },
        )

    assert response.status_code == 200
    assert response.json["status"] == "completed"
    engine.credit_views.assert_called_once_with(
        "user-1", 25, reason="pack_purchase",
        ref_id="order-pack-1", source="payment_status"
    )


def test_paid_document_unlocks_buyer_and_credits_creator():
    from app import app

    client = app.test_client()
    with client.session_transaction() as session:
        session["user"] = {"uid": "buyer-1", "email": "buyer@example.com"}

    with patch("routes.payments.init_supabase", return_value=None), \
         patch("data.transactions.is_order_completed", return_value=False), \
         patch("data.transactions.save_transaction_record"), \
         patch("methods.wallet_service.credit_creator_for_purchase") as credit_creator, \
         patch("methods.wallet_service.get_document_creator", return_value="seller-1"), \
         patch("methods.creator_crm_service.record_creator_customer_purchase"):
        response = client.post(
            "/api/payment/status",
            json={
                "order_id": "order-doc-1",
                "utr": "123456789013",
                "amount": "49",
                "purpose": "Document-doc-1",
            },
        )

    assert response.status_code == 200
    with client.session_transaction() as session:
        assert "doc-1" in session["purchased_documents"]
    credit_creator.assert_called_once()


def test_replayed_payment_does_not_credit_again():
    from app import app

    with patch("data.transactions.is_order_completed", return_value=True):
        response = app.test_client().post(
            "/api/payment/status",
            json={
                "order_id": "order-already-paid",
                "utr": "123456789014",
                "amount": "50",
                "purpose": "Credits-25",
            },
        )
    assert response.status_code == 200
    assert response.json["already_fulfilled"] is True
