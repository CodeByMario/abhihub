import os

import pytest

os.environ.setdefault('SECRET_KEY', 'test-api-rate-limit-key')
os.environ.setdefault('SUPABASE_URL', 'https://mock-supabase.supabase.co')
os.environ.setdefault('SUPABASE_KEY', 'mock-supabase-key')

from app import app
from methods.api_rate_limiter import clear_api_rate_limits


@pytest.fixture(autouse=True)
def reset_rate_limit_state():
    clear_api_rate_limits()
    yield
    clear_api_rate_limits()


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as test_client:
        yield test_client


def _set_session_user(client, uid):
    with client.session_transaction() as session:
        session['user'] = {'uid': uid, 'email': f'{uid}@example.test'}


def test_api_limit_is_per_authenticated_user(client, monkeypatch):
    monkeypatch.setenv('API_RATE_LIMIT_PER_USER', '1')
    first = app.test_client()
    second = app.test_client()
    _set_session_user(first, 'rate-limit-user-1')
    _set_session_user(second, 'rate-limit-user-2')

    assert first.get('/api/nonexistent-rate-limit-check').status_code == 404
    assert first.get('/api/nonexistent-rate-limit-check').status_code == 429
    assert second.get('/api/nonexistent-rate-limit-check').status_code == 404


def test_anonymous_limit_uses_socket_peer_not_forwarded_header(client, monkeypatch):
    monkeypatch.setenv('API_RATE_LIMIT_PER_IP', '1')
    assert client.get(
        '/api/nonexistent-forwarded-header-check', headers={'X-Forwarded-For': '198.51.100.1'}
    ).status_code == 404
    response = client.get(
        '/api/nonexistent-forwarded-header-check', headers={'X-Forwarded-For': '203.0.113.2'}
    )
    assert response.status_code == 429
    assert response.headers['Retry-After']


def test_webhooks_and_preflight_are_exempt(client, monkeypatch):
    monkeypatch.setenv('API_RATE_LIMIT_PER_IP', '1')
    first = client.post('/api/webhooks/not-a-real-provider-route')
    second = client.post('/api/webhooks/not-a-real-provider-route')
    assert first.status_code != 429
    assert second.status_code != 429
    assert client.options('/api/nonexistent-preflight-check').status_code != 429


def test_unprefixed_token_auth_endpoint_is_rate_limited(client, monkeypatch):
    monkeypatch.setenv('API_RATE_LIMIT_PER_IP', '1')
    first = client.post('/auth', json={})
    second = client.post('/auth', json={})
    assert first.status_code == 401
    assert second.status_code == 429
