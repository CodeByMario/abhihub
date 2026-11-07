import os

import pytest

os.environ.setdefault('SECRET_KEY', 'test-sensitive-error-key')
os.environ.setdefault('SUPABASE_URL', 'https://mock-supabase.supabase.co')
os.environ.setdefault('SUPABASE_KEY', 'mock-supabase-key')

from app import app
from methods.api_rate_limiter import clear_api_rate_limits


@pytest.fixture(autouse=True)
def reset_rate_limit_state():
    clear_api_rate_limits()
    yield
    clear_api_rate_limits()


def test_payment_provider_exception_is_not_returned_or_logged(monkeypatch, caplog):
    # Use a local fixture setup to keep this test independent of other app tests.
    app.config['TESTING'] = True
    from methods import razorpay_service
    from routes import payments

    sentinel = 'provider-private-response-sentinel'

    def fail_order(**_kwargs):
        raise RuntimeError(sentinel)

    monkeypatch.setattr(razorpay_service, 'create_order', fail_order)
    monkeypatch.setattr(payments, 'init_supabase', lambda: None)

    with app.test_client() as test_client:
        with test_client.session_transaction() as session:
            session['user'] = {'uid': 'payment-test-user', 'email': 'payment@example.test'}
        response = test_client.post('/api/payment/initiate', json={'amount': 49})

    assert response.status_code == 500
    assert sentinel.encode() not in response.data
    assert sentinel not in caplog.text


def test_wallet_database_exception_is_not_returned_or_logged(monkeypatch, caplog):
    from methods import wallet_service

    sentinel = 'wallet-database-private-sentinel'

    class FailingDatabase:
        def table(self, _name):
            raise RuntimeError(sentinel)

    monkeypatch.setattr(wallet_service, 'supabase', FailingDatabase())
    result = wallet_service.get_creator_wallet('wallet-test-user')

    assert result['success'] is False
    assert sentinel not in repr(result)
    assert sentinel not in caplog.text


@pytest.mark.parametrize(
    ('method', 'path', 'payload'),
    [
        ('get', '/api/document/test-document/pricing', None),
        ('post', '/api/document/test-document/coupon', {'coupon_code': 'TEST'}),
    ],
)
def test_document_payment_database_errors_are_generic(method, path, payload, monkeypatch, caplog):
    from routes import payments

    sentinel = 'payment-database-private-sentinel'

    def fail_database():
        raise RuntimeError(sentinel)

    monkeypatch.setattr(payments, 'init_supabase', fail_database)
    with app.test_client() as test_client:
        response = getattr(test_client, method)(path, json=payload)

    assert response.status_code == 500
    assert sentinel.encode() not in response.data
    assert sentinel not in caplog.text


def test_file_url_signing_exception_is_not_returned_or_logged(monkeypatch, caplog):
    from firebase_admin import storage

    app.config['TESTING'] = True
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', False)
    sentinel = 'firebase-private-signing-sentinel'

    class Blob:
        def exists(self):
            return True

        def generate_signed_url(self, **_kwargs):
            raise RuntimeError(sentinel)

    class Bucket:
        def blob(self, _path):
            return Blob()

    monkeypatch.setattr(storage, 'bucket', lambda: Bucket())
    with app.test_client() as test_client:
        with test_client.session_transaction() as session:
            session['user'] = {'uid': 'file-signing-test-user'}
        response = test_client.post('/get-file-url', json={'file_path': 'private/doc.pdf'})

    assert response.status_code == 500
    assert sentinel.encode() not in response.data
    assert sentinel not in caplog.text


def test_file_verification_exception_is_not_returned_or_logged(monkeypatch, caplog):
    from firebase_admin import storage

    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', False)
    sentinel = 'firebase-private-verification-sentinel'

    def fail_bucket():
        raise RuntimeError(sentinel)

    monkeypatch.setattr(storage, 'bucket', fail_bucket)
    with app.test_client() as test_client:
        response = test_client.post('/verify-file', json={'file_path': 'private/doc.pdf'})

    assert response.status_code == 500
    assert sentinel.encode() not in response.data
    assert sentinel not in caplog.text


def test_admin_database_exception_is_not_returned_or_logged(monkeypatch, caplog):
    from routes import admin

    sentinel = 'admin-database-secret-sentinel'

    class FailingDatabase:
        def table(self, _name):
            raise RuntimeError(sentinel)

    monkeypatch.setattr(admin, 'supabase', FailingDatabase())
    with app.test_client() as test_client:
        with test_client.session_transaction() as session:
            session['user'] = {'uid': 'admin-test-user', 'role': 'admin'}
        response = test_client.get('/api/admin/payment/transactions')

    assert response.status_code == 500
    assert sentinel.encode() not in response.data
    assert sentinel not in caplog.text
