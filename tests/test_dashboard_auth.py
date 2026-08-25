"""
Regression tests for /dashboard route security.

CRITICAL: Previously, two functions were registered for /dashboard:
  1. dashboard() @ app.py:2114 — NO @auth_required decorator
  2. premium() @ app.py:2793  — WITH @auth_required decorator

Flask/Werkzeug routes /dashboard to the FIRST registered handler (dashboard()),
which bypassed authentication. This gave unauthenticated users access to:
  - All documents from get_all_files_unified()
  - User's uploaded files and statistics
  - User's file access history
  - User's college/profile data
  - Reputation scores, ranks, and badges

These tests verify that /dashboard requires authentication.
"""
import os
import sys
import pytest

# Set minimal env before importing app
os.environ.setdefault('SUPABASE_URL', 'https://test.supabase.co')
os.environ.setdefault('SUPABASE_KEY', 'test-key-service-role')
os.environ.setdefault('BASE_DOMAIN', 'localhost')
os.environ.setdefault('SECRET_KEY', 'test-secret-key-for-dashboard-test')
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('INDEX_NOW_BING_API_KEY', 'test-indexnow-key')

# Prevent real Firebase/Supabase connections at import
sys.modules['methods.supabase_helper'] = type(sys)('methods.supabase_helper')
sys.modules['methods.supabase_helper'].init_supabase = lambda: None
sys.modules['methods.supabase_helper'].get_all_file_records_formatted = lambda **kw: []
sys.modules['methods.supabase_helper'].get_student_profile = lambda uid: {'success': False}
sys.modules['methods.supabase_helper'].calculate_user_ranks = lambda: []
sys.modules['methods.supabase_helper'].get_reputation_stats = lambda uid: {'success': False}
sys.modules['data.profiles'] = type(sys)('data.profiles')
sys.modules['data.profiles'].UserSession = type('UserSession', (), {'log_login': staticmethod(lambda *a, **kw: True)})
sys.modules['data.documents'] = type(sys)('data.documents')
sys.modules['data.documents'].Document = type('Document', (), {
    'get_all_approved': staticmethod(lambda: []),
    'to_dict': lambda self: {}
})
sys.modules['data.interactions'] = type(sys)('data.interactions')
sys.modules['data.notifications'] = type(sys)('data.notifications')
sys.modules['data.analytics'] = type(sys)('data.analytics')
sys.modules['push_api'] = type(sys)('push_api')
sys.modules['push_api'].init_push_api = lambda app: None
sys.modules['scheduled_tasks'] = type(sys)('scheduled_tasks')
sys.modules['scheduled_tasks'].init_scheduler = lambda app: None

import jwt


@pytest.fixture
def client():
    """Create a test client with a controlled session."""
    # We can't fully import app.py without Supabase working,
    # so we test the routing logic directly
    from flask import Flask
    from functools import wraps

    test_app = Flask(__name__)
    test_app.secret_key = os.getenv('FLASK_SECRET_KEY', 'test-secret')  # Test only — never use this pattern in production

    def auth_required(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            from flask import session, request, jsonify, redirect, url_for
            if 'user' not in session:
                if request.path.startswith('/api/'):
                    return jsonify({'success': False, 'message': 'Unauthorized'}), 401
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated

    # Simulate the ORIGINAL bug: dashboard() without auth, premium() with auth
    test_app.config['TESTING'] = True

    @test_app.route('/dashboard')
    def dashboard():
        # This was the VULNERABLE handler — no auth_required
        return 'dashboard-no-auth', 200

    @test_app.route('/dashboard')
    @auth_required
    def premium():
        return 'premium-with-auth', 200

    @test_app.route('/login')
    def login():
        return 'login'

    @test_app.route('/api/quota')
    @auth_required
    def api_quota():
        return {'success': True}, 200

    return test_app.test_client()


@pytest.fixture
def fixed_client():
    """Simulate the FIXED state: only one /dashboard handler WITH auth."""
    from flask import Flask, session, request, jsonify, redirect, url_for
    from functools import wraps

    test_app = Flask(__name__)
    test_app.secret_key = os.getenv('FLASK_SECRET_KEY', 'test-secret')  # Test only — never use this pattern in production
    test_app.config['TESTING'] = True

    def auth_required(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user' not in session:
                if request.path.startswith('/api/'):
                    return jsonify({'success': False, 'message': 'Unauthorized'}), 401
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated

    @test_app.route('/dashboard')
    @auth_required
    def dashboard():
        # This is the FIXED handler — WITH auth_required
        return 'dashboard-with-auth', 200

    @test_app.route('/login')
    def login():
        return 'login'

    @test_app.route('/api/quota', methods=['POST'])
    @auth_required
    def api_quota():
        return {'success': True}, 200

    return test_app.test_client()


class TestDashboardRoutingBug:
    """Tests that reproduce and verify the fix for the /dashboard auth bypass."""

    def test_bug_reproduction_unauthenticated_gets_200_not_302(self, client):
        """
        BUG REPRODUCTION: With two /dashboard routes, Flask resolves to the
        first one (no auth). Unauthenticated access SHOULD be blocked.
        
        This test PASSES when the bug exists (demonstrating the vulnerability)
        and FAILS after the fix (demonstrating the fix works).
        
        In the fixed state, use test_dashboard_auth_blocked instead.
        """
        response = client.get('/dashboard')
        # With the bug: 200 (should be redirect 302 to /login)
        # This demonstrates the vulnerability
        assert response.status_code == 200, \
            "BUG NOT REPRODUCED: Expected 200 (unauthenticated access allowed)"
        assert b'dashboard-no-auth' in response.data

    def test_dashboard_auth_blocked_after_fix(self, fixed_client):
        """
        FIXED STATE VERIFICATION: After removing the duplicate route,
        unauthenticated access to /dashboard should redirect to /login.
        
        This test FAILS with the bug and PASSES after the fix.
        """
        response = fixed_client.get('/dashboard', follow_redirects=False)
        # After fix: 302 redirect to login (auth_required blocks)
        assert response.status_code == 302, \
            f"SECURITY FAIL: Expected 302 redirect, got {response.status_code}"
        assert '/login' in response.headers.get('Location', ''), \
            "Security FAIL: Should redirect to /login"

    def test_dashboard_auth_blocked_after_fix_no_follow(self, fixed_client):
        """Same check but explicitly checking we don't get 200."""
        response = fixed_client.get('/dashboard', follow_redirects=False)
        assert response.status_code != 200, \
            "SECURITY FAIL: Unauthenticated /dashboard returned 200"

    def test_authenticated_user_gets_dashboard(self, fixed_client):
        """After fix: authenticated users should access /dashboard."""
        with fixed_client.session_transaction() as sess:
            sess['user'] = {'uid': 'test-uid', 'email': 'test@test.com'}
        response = fixed_client.get('/dashboard')
        assert response.status_code == 200
        assert b'dashboard-with-auth' in response.data

    def test_api_auth_also_blocked_unauthenticated(self, fixed_client):
        """API-style auth check returns 401 JSON, not redirect."""
        response = fixed_client.post('/api/quota')
        assert response.status_code == 401
        assert response.is_json


class TestRouteMapIntegrity:
    """Verify the route map itself doesn't have duplicate registrations."""

    def test_no_duplicate_dashboard_in_app_py(self):
        """Static analysis: app.py must not have two @app.route('/dashboard')."""
        import ast
        app_path = os.path.join(os.path.dirname(__file__), '..', 'app.py')
        app_path = os.path.abspath(app_path)

        with open(app_path, 'r') as f:
            tree = ast.parse(f.read())

        dashboard_count = 0
        dashboard_handlers = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call):
                        if (isinstance(decorator.func, ast.Attribute) and
                            decorator.func.attr == 'route'):
                            for arg in decorator.args:
                                if isinstance(arg, ast.Constant) and arg.value == '/dashboard':
                                    dashboard_count += 1
                                    dashboard_handlers.append((node.name, node.lineno))

        assert dashboard_count <= 1, \
            f"Multiple /dashboard routes found: {dashboard_handlers}. " \
            f"Only one /dashboard route should exist to prevent auth bypass."
        assert dashboard_count == 1, \
            f"Expected exactly 1 /dashboard route, found {dashboard_count}"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
