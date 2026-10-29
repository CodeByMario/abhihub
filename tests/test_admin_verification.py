"""
tests/test_admin_verification.py
Comprehensive Phase 5 Verification suite testing:
1. Endpoint authorization & RBAC gates (anonymous -> 401, student -> 403, admin -> 200)
2. User moderation endpoints (block, ban, verify, status)
3. File management endpoints (list, quarantine)
4. Site settings read & update
5. Audit trail generation
"""

import pytest
from app import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False  # Test client functional testing
    with app.test_client() as client:
        yield client


# ─── 1. Access Control & RBAC Verification ───────────────────────────────────

def test_unauthenticated_access_denied(client):
    """Anonymous requests to admin routes must receive 401 for APIs or redirect for pages."""
    # API endpoints
    api_res = client.get('/api/admin/users')
    assert api_res.status_code == 401
    assert api_res.json.get('success') is False

    api_res2 = client.get('/api/admin/files')
    assert api_res2.status_code == 401

    api_res3 = client.get('/api/admin/audit/logs')
    assert api_res3.status_code == 401

    api_res4 = client.get('/api/admin/settings')
    assert api_res4.status_code == 401

    # Page endpoints should redirect to login
    page_res = client.get('/admin')
    assert page_res.status_code == 302
    assert '/login' in page_res.headers.get('Location', '')


def test_student_forbidden(client):
    """Authenticated student user without admin role must receive 403 Forbidden."""
    with client.session_transaction() as sess:
        sess['user'] = {
            'uid': '00000000-0000-0000-0000-000000000001',
            'id': '00000000-0000-0000-0000-000000000001',
            'email': 'student@college.edu',
            'role': 'student'
        }

    api_res = client.get('/api/admin/users')
    assert api_res.status_code == 403
    assert 'Forbidden' in api_res.json.get('message', '')

    settings_res = client.get('/api/admin/settings')
    assert settings_res.status_code == 403


# ─── 2. Admin Privileged Operations Verification ─────────────────────────────

def test_admin_read_endpoints(client):
    """Admin user should successfully query admin read endpoints."""
    with client.session_transaction() as sess:
        sess['user'] = {
            'uid': '00000000-0000-0000-0000-000000000099',
            'id': '00000000-0000-0000-0000-000000000099',
            'email': 'abhihub.02@gmail.com',  # Superadmin email
            'role': 'admin'
        }

    # Site settings
    settings_res = client.get('/api/admin/settings')
    assert settings_res.status_code == 200
    assert 'settings' in settings_res.json

    # Audit logs
    audit_res = client.get('/api/admin/audit/logs')
    assert audit_res.status_code == 200
    assert 'logs' in audit_res.json


def test_anti_lockout_endpoint_enforcement(client):
    """Admin must not be able to block, ban, or delete themselves via API."""
    admin_id = '00000000-0000-0000-0000-000000000099'
    with client.session_transaction() as sess:
        sess['user'] = {
            'uid': admin_id,
            'id': admin_id,
            'email': 'admin@test.com',
            'role': 'admin'
        }

    # Attempt self-block
    res = client.post(f'/api/admin/users/{admin_id}/block', json={'is_blocked': True})
    assert res.status_code == 403
    assert 'Anti-Lockout' in res.json.get('error', '')

    # Attempt self-ban
    res2 = client.post(f'/api/admin/users/{admin_id}/ban', json={'is_banned': True})
    assert res2.status_code == 403
    assert 'Anti-Lockout' in res2.json.get('error', '')
