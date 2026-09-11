"""
Production Readiness Verification Test Suite for AbhiHub.
Verifies health probes, security headers, auth boundaries, upload constraints, and analytics privacy.
Compatible with standard library unittest and pytest.
"""

import os
import io
import unittest
from app import app, validate_file_content, allowed_file


class ProductionReadinessTestCase(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

    def test_health_check_endpoints(self):
        """Verify health endpoints respond with 200 and healthy status."""
        for path in ['/health', '/api/health']:
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data['status'], 'healthy')
            self.assertEqual(data['service'], 'abhihub')
            self.assertIn('timestamp', data)

    def test_global_security_headers(self):
        """Verify standard security headers are attached to responses."""
        res = self.client.get('/health')
        self.assertEqual(res.headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(res.headers.get('X-Frame-Options'), 'SAMEORIGIN')
        self.assertEqual(res.headers.get('Referrer-Policy'), 'strict-origin-when-cross-origin')
        self.assertIn('camera=(self)', res.headers.get('Permissions-Policy', ''))

    def test_unauthenticated_protected_routes(self):
        """Verify unauthenticated requests to protected endpoints return 401."""
        res = self.client.get('/api/profile-status')
        self.assertEqual(res.status_code, 401)
        self.assertFalse(res.get_json().get('success'))

        res = self.client.post('/api/ask-paper', json={'doc_id': '123', 'question': 'test'})
        self.assertEqual(res.status_code, 401)

    def test_upload_file_validation(self):
        """Verify allowed_file and validate_file_content reject disallowed and invalid types."""
        # Extensions check
        self.assertTrue(allowed_file('document.pdf'))
        self.assertTrue(allowed_file('image.png'))
        self.assertTrue(allowed_file('photo.jpg'))
        self.assertFalse(allowed_file('script.php'))
        self.assertFalse(allowed_file('malicious.exe'))
        self.assertFalse(allowed_file('vector.svg'))  # SVGs restricted for stored XSS protection
        self.assertFalse(allowed_file('noextension'))

        # Magic byte validation
        pdf_stream = io.BytesIO(b'%PDF-1.4\n%...\n')
        self.assertTrue(validate_file_content(pdf_stream, 'test.pdf'))

        fake_pdf = io.BytesIO(b'<script>alert(1)</script>')
        self.assertFalse(validate_file_content(fake_pdf, 'fake.pdf'))

        png_stream = io.BytesIO(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR')
        self.assertTrue(validate_file_content(png_stream, 'test.png'))

        jpg_stream = io.BytesIO(b'\xff\xd8\xff\xe0\x00\x10JFIF')
        self.assertTrue(validate_file_content(jpg_stream, 'test.jpg'))

    def test_analytics_privacy_zero_pii(self):
        """Verify analytics user-properties endpoint leaks zero PII."""
        res = self.client.get('/api/analytics/user-properties')
        self.assertEqual(res.status_code, 200)
        props = res.get_json().get('userProperties', {})
        
        # Must not contain email or password or phone
        self.assertNotIn('email', props)
        self.assertNotIn('password', props)
        self.assertNotIn('mobile', props)
        self.assertNotIn('phone', props)
        self.assertEqual(props.get('userId'), 'anonymous')

    def test_logout_session_purged(self):
        """Verify /logout clears cookies and sessions."""
        with self.client.session_transaction() as sess:
            sess['user'] = {'uid': 'test-user-123', 'name': 'Tester'}

        res = self.client.get('/logout')
        self.assertEqual(res.status_code, 200)
        cookie_headers = res.headers.getlist('Set-Cookie')
        self.assertTrue(any('session=;' in c or 'expires=' in c.lower() or 'Max-Age=0' in c for c in cookie_headers))

    def test_error_handlers(self):
        """Verify 404 handler returns structured HTML error page without sensitive traceback."""
        res = self.client.get('/this-path-definitely-does-not-exist-404')
        self.assertEqual(res.status_code, 404)
        self.assertIn(b"Page Not Found", res.data)


if __name__ == '__main__':
    unittest.main()
