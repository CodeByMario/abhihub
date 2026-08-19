import json
import os
import unittest

from app import app


class DeleteAccountFormTests(unittest.TestCase):
    def setUp(self):
        app.testing = True
        self.client = app.test_client()
        self.request_file = 'data/account_deletion_requests.json'
        if os.path.exists(self.request_file):
            os.remove(self.request_file)

    def test_delete_account_form_stores_user_details(self):
        response = self.client.post('/delete-account', data={
            'full_name': 'Jane Doe',
            'email': 'jane@example.com',
            'username': 'jane',
            'reason': 'I no longer need the account',
            'details': 'Please remove all my data',
            'confirm_deletion': 'on',
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Request received', response.data)

        with open(self.request_file, 'r', encoding='utf-8') as fh:
            data = json.load(fh)

        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['full_name'], 'Jane Doe')
        self.assertEqual(data[0]['email'], 'jane@example.com')
        self.assertEqual(data[0]['reason'], 'I no longer need the account')


if __name__ == '__main__':
    unittest.main()
