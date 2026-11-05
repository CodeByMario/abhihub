import unittest
from unittest.mock import MagicMock, patch
import json
from app import app, has_document_access

class TestNotesMonetization(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config['TESTING'] = True

    def test_has_document_access_free_document(self):
        with app.test_request_context():
            doc = {'id': 'doc1', 'uploader_id': 'user1', 'description': 'Simple notes'}
            self.assertTrue(has_document_access(None, 'doc1', doc))

    def test_has_document_access_paid_anonymous(self):
        with app.test_request_context():
            doc = {
                'id': 'doc2',
                'uploader_id': 'seller1',
                'description': json.dumps({'text_description': 'Notes', 'pricing': {'is_paid': True, 'price': 99.0, 'seller_id': 'seller1'}})
            }
            self.assertFalse(has_document_access(None, 'doc2', doc))

    def test_has_document_access_seller(self):
        with app.test_request_context():
            doc = {
                'id': 'doc3',
                'uploader_id': 'seller1',
                'description': json.dumps({'text_description': 'Notes', 'pricing': {'is_paid': True, 'price': 99.0, 'seller_id': 'seller1'}})
            }
            self.assertTrue(has_document_access('seller1', 'doc3', doc))

    def test_has_document_access_session_unlocked(self):
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess['purchased_documents'] = ['doc4']
            with app.test_request_context():
                from flask import session
                doc = {
                    'id': 'doc4',
                    'uploader_id': 'seller1',
                    'description': json.dumps({'text_description': 'Notes', 'pricing': {'is_paid': True, 'price': 99.0, 'seller_id': 'seller1'}})
                }
                # Check within context of session
                with patch('app.session', {'purchased_documents': ['doc4']}):
                    self.assertTrue(has_document_access('buyer1', 'doc4', doc))

    def test_extract_document_pricing(self):
        from app import extract_document_pricing
        doc = {
            'description': json.dumps({'text_description': 'Unit 1 Notes', 'pricing': {'is_paid': True, 'price': 29.0, 'seller_id': 'seller1'}})
        }
        pricing = extract_document_pricing(doc)
        self.assertTrue(pricing.get('is_paid'))
        self.assertEqual(pricing.get('price'), 29.0)

if __name__ == '__main__':
    unittest.main()
