import pytest
from app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['APP_SHELL_ENABLED'] = True
    with app.test_client() as client:
        yield client

def test_app_shell_unauth(client):
    res = client.get('/app-shell')
    assert res.status_code == 302
    assert '/login' in res.headers.get('Location', '')

def test_app_shell_authenticated_valid_p(client):
    with client.session_transaction() as sess:
        sess['user'] = {'uid': 'usr_1', 'email': 'student@example.com'}
    res = client.get('/app-shell?p=/upload')
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert 'src="/upload"' in html
    assert 'frame-ancestors \'self\'' in res.headers.get('Content-Security-Policy', '')

def test_app_shell_sanitizes_p(client):
    with client.session_transaction() as sess:
        sess['user'] = {'uid': 'usr_1', 'email': 'student@example.com'}

    bad_paths = [
        '//evil.com',
        '/\\evil.com',
        '\\evil.com',
        'javascript:alert(1)',
        '/app-shell',
        '/login',
        '/signup',
        '/logout',
        '/auth/callback',
        '/offline',
        '/api/some-endpoint'
    ]
    for bp in bad_paths:
        res = client.get(f'/app-shell?p={bp}')
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert 'src="/dashboard"' in html

def test_ai_embed_csp_unaffected(client):
    res = client.get('/ai/embed')
    assert res.status_code == 200
    csp = res.headers.get('Content-Security-Policy', '')
    assert 'https://*.abhihub.edu.eu.org' in csp
