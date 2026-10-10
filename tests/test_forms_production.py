"""
Production Form Verification & Edge Case Test Suite for AbhiHub.
Covers all 8 key application forms: Contact, Upload, Settings, Delete Account,
Know-Me Creator, Notes Monetization, AI Chat/Ask-Paper, Admin Notifications.
"""

import os
import io
import json
import unittest
from unittest.mock import patch, MagicMock
from app import app, allowed_file, validate_file_content

class ProductionFormsTestCase(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

    # 1. Contact Form
    def test_contact_form_page_renders(self):
        res = self.client.get('/contact')
        self.assertEqual(res.status_code, 200)

    def test_contact_form_turnstile_missing_secret(self):
        with patch.dict(os.environ, {'TURNSTILE_SECRET': ''}):
            res = self.client.post('/api/contact', json={'turnstile_token': 'dummy', 'name': 'A', 'email': 'a@a.com', 'message': 'hi'})
            self.assertEqual(res.status_code, 500)

    @patch('requests.post')
    def test_contact_form_turnstile_bot_failure(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {'success': False}
        with patch.dict(os.environ, {'TURNSTILE_SECRET': 'test_secret'}):
            res = self.client.post('/api/contact', json={'turnstile_token': 'bad_token', 'name': 'A', 'email': 'a@a.com', 'message': 'hi'})
            self.assertEqual(res.status_code, 403)

    @patch('requests.post')
    def test_contact_form_success(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {'success': True}
        with patch.dict(os.environ, {'TURNSTILE_SECRET': 'test_secret'}):
            res = self.client.post('/api/contact', json={
                'turnstile_token': 'valid_token',
                'name': 'Test User',
                'email': 'test@example.com',
                'subject': 'Inquiry',
                'message': 'Testing message body'
            })
            self.assertEqual(res.status_code, 200)
            self.assertTrue(res.get_json().get('success'))

    @patch('requests.post')
    def test_contact_form_invalid_inputs(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {'success': True}
        with patch.dict(os.environ, {'TURNSTILE_SECRET': 'test_secret'}):
            # Invalid email format
            res = self.client.post('/api/contact', json={
                'turnstile_token': 'valid_token',
                'name': 'Test User',
                'email': 'not-an-email',
                'message': 'Testing message body'
            })
            self.assertEqual(res.status_code, 400)

            # Empty message
            res = self.client.post('/api/contact', json={
                'turnstile_token': 'valid_token',
                'name': 'Test User',
                'email': 'valid@example.com',
                'message': '   '
            })
            self.assertEqual(res.status_code, 400)

    # 2. Upload Form & Magic Bytes
    def test_upload_page_unauthenticated_behavior(self):
        res = self.client.get('/upload', follow_redirects=False)
        self.assertIn(res.status_code, [200, 302])

    def test_upload_disallowed_extensions(self):
        for ext in ['evil.exe', 'shell.php', 'script.js', 'vector.svg', 'binary.bin']:
            self.assertFalse(allowed_file(ext))

    def test_upload_allowed_extensions(self):
        for ext in ['paper.pdf', 'shot.png', 'photo.jpg', 'image.webp']:
            self.assertTrue(allowed_file(ext))

    def test_upload_magic_bytes_inspection(self):
        fake_pdf = io.BytesIO(b'NOT A PDF CONTENT')
        self.assertFalse(validate_file_content(fake_pdf, 'sample.pdf'))
        real_pdf = io.BytesIO(b'%PDF-1.5 test document content')
        self.assertTrue(validate_file_content(real_pdf, 'sample.pdf'))

    # 3. Account / Settings
    def test_account_update_unauthenticated(self):
        res = self.client.post('/account/update', data={'display_name': 'Hacker'})
        self.assertIn(res.status_code, [302, 400, 401, 403, 404])

    # 4. Account Deletion Route
    def test_delete_account_unauthenticated(self):
        res = self.client.get('/delete-account', follow_redirects=False)
        self.assertIn(res.status_code, [302, 401])

    def test_delete_account_page_authenticated(self):
        with self.client.session_transaction() as sess:
            sess['user'] = {'uid': 'u1', 'email': 'u1@example.com'}
        res = self.client.get('/delete-account')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Delete Your Account', res.data)

    # 5. Know-Me / MemoryWall Creation Form
    def test_know_me_create_unauthenticated(self):
        res = self.client.get('/memorywall/create', follow_redirects=False)
        # Should redirect or require auth
        self.assertIn(res.status_code, [302, 401])

    # 6. Monetization / Store Room
    def test_document_pricing_helpers(self):
        from data.pricing import extract_document_pricing, has_document_access
        doc = {'id': 'd1', 'pricing': {'is_paid': True, 'price': 49.0, 'seller_id': 'u1'}}
        pricing = extract_document_pricing(doc)
        self.assertTrue(pricing.get('is_paid'))
        self.assertEqual(pricing.get('price'), 49.0)
        with app.test_request_context():
            # Anonymous should not have access to paid doc
            self.assertFalse(has_document_access(None, 'd1', doc))
            # Seller should have access
            self.assertTrue(has_document_access('u1', 'd1', doc))

    def test_store_room_labeling_unauthenticated(self):
        res = self.client.post('/store-room/api/label', json={'filename': 'test.pdf'})
        self.assertIn(res.status_code, [302, 401])

    def test_store_room_labeling_missing_fields(self):
        with self.client.session_transaction() as sess:
            sess['user'] = {'uid': 'u1', 'email': 'u1@example.com'}
        res = self.client.post('/store-room/api/label', json={'filename': ''})
        self.assertEqual(res.status_code, 400)

    @patch('routes.store_room.save_file_record')
    @patch('routes.store_room.verify_hierarchy', return_value=True)
    @patch('routes.store_room._mark_labeled')
    @patch('routes.store_room.log_label_audit')
    def test_store_room_labeling_success(self, mock_audit, mock_mark, mock_hier, mock_save):
        mock_save.return_value = {'success': True, 'data': {'id': 'doc_123'}}
        with self.client.session_transaction() as sess:
            sess['user'] = {'uid': 'u1', 'email': 'u1@example.com'}
        res = self.client.post('/store-room/api/label', json={
            'filename': 'physics_2024.pdf',
            'url': 'https://example.com/physics_2024.pdf',
            'subject_name': 'Physics',
            'subject_id': 'sub_1',
            'year': 2024,
            'college_id': 'col_1',
            'branch_id': 'cse',
            'document_category': 'papers'
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json().get('success'))


    # 7. AI Chat / Ask-Paper Form
    def test_ask_paper_unauthenticated(self):
        res = self.client.post('/api/ask-paper', json={'doc_id': 'xyz', 'question': 'What is this?'})
        self.assertEqual(res.status_code, 401)

    # 8. Admin Notifications Form
    def test_admin_notification_unauthenticated(self):
        res = self.client.post('/api/admin/notifications/send', json={'title': 'Alert', 'message': 'Test'})
        self.assertIn(res.status_code, [302, 401, 403, 404])

    # 9. Dropdown Data & Hierarchy Endpoints
    def test_dropdown_hierarchy_endpoints(self):
        res_col = self.client.get('/api/colleges')
        self.assertEqual(res_col.status_code, 200)
        self.assertTrue(res_col.get_json().get('success'))

        res_dept = self.client.get('/api/departments')
        self.assertEqual(res_dept.status_code, 200)
        self.assertTrue(res_dept.get_json().get('success'))

        res_subj = self.client.get('/api/subjects')
        self.assertEqual(res_subj.status_code, 200)
        self.assertTrue(res_subj.get_json().get('success'))

if __name__ == '__main__':
    unittest.main()
