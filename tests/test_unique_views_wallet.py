import unittest
from unittest.mock import MagicMock, patch
from methods.wallet_service import get_creator_views_and_earnings, request_withdrawal, VIEW_EARNING_RATE_INR
from data.interactions import DocumentView

class TestUniqueViewsAndWallet(unittest.TestCase):

    @patch('data.interactions.get_client')
    def test_document_view_self_view_blocked(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        user_uuid = '3b135f8c-f872-4c50-ad33-2fcc0b9bda97'
        doc_uuid = '6f46a0d0-13e5-443b-8eb4-85e701e00f1c'
        # When doc owner is the same as user_id
        mock_client.table().select().eq().limit().execute.return_value.data = [{'uploader_id': user_uuid}]

        res = DocumentView.log_view(user_id=user_uuid, document_id=doc_uuid)
        self.assertTrue(res.get('skipped'))
        self.assertEqual(res.get('message'), 'Owner view not eligible')

    @patch('data.interactions.get_client')
    def test_document_view_duplicate_blocked(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        owner_uuid = '11111111-1111-4111-8111-111111111111'
        viewer_uuid = '22222222-2222-4222-8222-222222222222'
        doc_uuid = '6f46a0d0-13e5-443b-8eb4-85e701e00f1c'
        # Owner is someone else
        mock_client.table('documents').select().eq().limit().execute.return_value.data = [{'uploader_id': owner_uuid}]
        # Existing view found
        mock_client.table(DocumentView.TABLE).select().eq().eq().limit().execute.return_value.data = [{'id': 'view-1'}]

        res = DocumentView.log_view(user_id=viewer_uuid, document_id=doc_uuid)
        self.assertTrue(res.get('duplicate'))
        self.assertEqual(res.get('message'), 'View already logged')

    @patch('methods.wallet_service.supabase')
    def test_creator_unique_views_calculation(self, mock_supabase):
        # RPC fails -> fallback to python calculation
        mock_supabase.rpc.side_effect = Exception("No RPC")
        # 2 documents for creator
        mock_supabase.table('documents').select().eq().execute.return_value.data = [
            {'id': 'doc-1'}, {'id': 'doc-2'}
        ]
        # Raw views: user A viewed doc-1 twice, creator viewed doc-1, user B viewed doc-2
        mock_supabase.table('document_views').select().in_().execute.return_value.data = [
            {'document_id': 'doc-1', 'user_id': 'user-A', 'ip_address': '1.1.1.1'},
            {'document_id': 'doc-1', 'user_id': 'user-A', 'ip_address': '1.1.1.1'}, # duplicate
            {'document_id': 'doc-1', 'user_id': 'creator-1', 'ip_address': '2.2.2.2'}, # self view
            {'document_id': 'doc-2', 'user_id': 'user-B', 'ip_address': '3.3.3.3'},
        ]

        unique_views, earnings = get_creator_views_and_earnings('creator-1')
        self.assertEqual(unique_views, 2) # Only (doc-1, user-A) and (doc-2, user-B)
        self.assertEqual(earnings, round(2 * VIEW_EARNING_RATE_INR, 2))

    @patch('methods.wallet_service.supabase')
    def test_double_withdrawal_blocked_when_pending(self, mock_supabase):
        mock_supabase.table('creator_payout_requests').select().eq().in_().limit().execute.return_value.data = [
            {'id': 'pending-payout-1'}
        ]
        payout_payload = {'vpa': 'test@upi', 'pan_number': 'ABCDE1234F', 'account_holder_name': 'Test User'}
        ok, msg = request_withdrawal('creator-1', 100.0, 'upi', payout_payload)
        self.assertFalse(ok)
        self.assertIn("under review", msg)

    @patch('methods.wallet_service.supabase')
    def test_process_payout_refund_accounting(self, mock_supabase):
        from methods.wallet_service import process_payout_request
        payout_id = 'payout-uuid-123'

        mock_wallets_table = MagicMock()
        mock_payouts_table = MagicMock()
        mock_ledger_table = MagicMock()

        def table_router(tbl):
            if tbl == 'creator_wallets':
                return mock_wallets_table
            elif tbl == 'creator_payout_requests':
                return mock_payouts_table
            elif tbl == 'wallet_ledger':
                return mock_ledger_table
            return MagicMock()

        mock_supabase.table.side_effect = table_router

        mock_payouts_table.select().eq().limit().execute.return_value.data = [{
            'id': payout_id,
            'creator_id': 'creator-1',
            'amount': 100.0,
            'status': 'pending',
            'payout_details': {'deducted_sales': 30.0, 'deducted_views': 70.0}
        }]
        mock_wallets_table.select().eq().limit().execute.return_value.data = [{
            'user_id': 'creator-1',
            'withdrawable_balance': 0.0,
            'total_withdrawn': 100.0
        }]

        ok, msg = process_payout_request(payout_id, 'rejected', admin_notes='Details incorrect')
        self.assertTrue(ok)
        mock_wallets_table.update.assert_called_with({
            'withdrawable_balance': 30.0,
            'total_withdrawn': 0.0,
            'updated_at': unittest.mock.ANY
        })
        mock_ledger_table.update.assert_called_with({'status': 'cancelled'})

    @patch('methods.wallet_service.get_creator_wallet')
    @patch('methods.wallet_service.supabase')
    def test_first_withdrawal_gamified_limit_5(self, mock_supabase, mock_get_wallet):
        mock_get_wallet.return_value = {
            'success': True,
            'wallet': {
                'withdrawable_balance': 15.0,
                'min_withdrawal': 5.0,
                'withdrawal_tier': 1
            }
        }
        mock_supabase.table('creator_payout_requests').select().eq().in_().limit().execute.return_value.data = []
        mock_supabase.table('creator_wallets').select().eq().limit().execute.return_value.data = [{
            'user_id': 'creator-1', 'withdrawable_balance': 0.0, 'total_withdrawn': 0.0
        }]
        mock_supabase.table('creator_payout_requests').insert().execute.return_value.data = [{'id': 'payout-1'}]

        payout_payload = {'vpa': 'test@okbank', 'pan_number': 'ABCDE1234F', 'account_holder_name': 'Test User'}
        # ₹5 should succeed
        ok, msg = request_withdrawal('creator-1', 5.0, 'upi', payout_payload)
        self.assertTrue(ok)

        # ₹4 should fail
        ok, msg = request_withdrawal('creator-1', 4.0, 'upi', payout_payload)
        self.assertFalse(ok)
        self.assertIn("5", msg)

    @patch('methods.wallet_service.get_creator_wallet')
    @patch('methods.wallet_service.supabase')
    def test_second_withdrawal_gamified_limit_25(self, mock_supabase, mock_get_wallet):
        mock_get_wallet.return_value = {
            'success': True,
            'wallet': {
                'withdrawable_balance': 30.0,
                'min_withdrawal': 25.0,
                'withdrawal_tier': 2
            }
        }
        mock_supabase.table('creator_payout_requests').select().eq().in_().limit().execute.return_value.data = []
        mock_supabase.table('creator_wallets').select().eq().limit().execute.return_value.data = [{
            'user_id': 'creator-1', 'withdrawable_balance': 0.0, 'total_withdrawn': 0.0
        }]
        mock_supabase.table('creator_payout_requests').insert().execute.return_value.data = [{'id': 'payout-2'}]

        payout_payload = {'vpa': 'test@okbank', 'pan_number': 'ABCDE1234F', 'account_holder_name': 'Test User'}
        # ₹25 should succeed
        ok, msg = request_withdrawal('creator-1', 25.0, 'upi', payout_payload)
        self.assertTrue(ok)

        # ₹20 should fail
        ok, msg = request_withdrawal('creator-1', 20.0, 'upi', payout_payload)
        self.assertFalse(ok)
        self.assertIn("25", msg)

    @patch('methods.wallet_service.get_creator_wallet')
    @patch('methods.wallet_service.supabase')
    def test_third_withdrawal_enforces_100_minimum_limit(self, mock_supabase, mock_get_wallet):
        # 2 or more past completed payouts -> min_withdrawal is 100.0, user trying ₹25 is blocked
        mock_get_wallet.return_value = {
            'success': True,
            'wallet': {
                'withdrawable_balance': 150.0,
                'min_withdrawal': 100.0,
                'withdrawal_tier': 3
            }
        }
        mock_supabase.table('creator_payout_requests').select().eq().in_().limit().execute.return_value.data = []

        payout_payload = {'vpa': 'test@okbank', 'pan_number': 'ABCDE1234F', 'account_holder_name': 'Test User'}
        ok, msg = request_withdrawal('creator-1', 25.0, 'upi', payout_payload)
        self.assertFalse(ok)
        self.assertIn("100", msg)


    @patch('methods.wallet_service.supabase')
    def test_commission_standard_and_early_promo(self, mock_supabase):
        from methods.wallet_service import calculate_fee_breakdown, get_creator_commission_pct

        # Standard creator: no registration or registered after Nov 8, 2026
        mock_supabase.table('profiles').select().eq().limit().execute.return_value.data = [{
            'created_at': '2026-11-15T10:00:00+00:00'
        }]
        std_breakdown = calculate_fee_breakdown(100.0, creator_id='user-late')
        self.assertEqual(std_breakdown['creator_pct'], 70)
        self.assertEqual(std_breakdown['creator_amount'], 70.0)
        self.assertEqual(std_breakdown['platform_fee'], 30.0)

        # Early creator registered before Nov 8, 2026 within 90 days
        mock_supabase.table('profiles').select().eq().limit().execute.return_value.data = [{
            'created_at': '2026-10-15T10:00:00+00:00'
        }]
        promo_breakdown = calculate_fee_breakdown(100.0, creator_id='user-early')
        self.assertEqual(promo_breakdown['creator_pct'], 90)
        self.assertEqual(promo_breakdown['creator_amount'], 90.0)
        self.assertEqual(promo_breakdown['platform_fee'], 10.0)
        self.assertTrue(promo_breakdown['is_promo'])

    @patch('methods.wallet_service.unlock_eligible_entries')
    @patch('methods.wallet_service.get_creator_views_and_earnings')
    @patch('methods.wallet_service.is_creator_verified')
    @patch('methods.wallet_service.supabase')
    def test_unverified_creator_hides_view_earnings(self, mock_supabase, mock_is_verified, mock_get_views, mock_unlock):
        from methods.wallet_service import get_creator_wallet

        mock_is_verified.return_value = False
        mock_get_views.return_value = (50, 10.0) # 50 views -> ₹10 raw
        mock_supabase.table('creator_wallets').select().eq().limit().execute.return_value.data = []
        mock_supabase.table('wallet_ledger').select().eq().eq().execute.return_value.data = []
        mock_supabase.table('creator_payout_requests').select().eq().execute.return_value.data = []
        mock_supabase.table('wallet_ledger').select().eq().order().limit().execute.return_value.data = []
        mock_supabase.table('creator_payout_requests').select().eq().order().limit().execute.return_value.data = []
        mock_supabase.table('profiles').select().eq().limit().execute.return_value.data = []

        w = get_creator_wallet('unverified-user')
        self.assertTrue(w['success'])
        wallet_info = w['wallet']
        self.assertFalse(wallet_info['is_verified'])
        self.assertFalse(wallet_info['is_view_monetized'])
        self.assertEqual(wallet_info['view_earnings'], 0.0)
        self.assertEqual(wallet_info['view_rate'], 0.0)


    def test_withdrawal_requires_valid_pan_and_bank(self):
        # Missing PAN
        ok, msg = request_withdrawal('creator-1', 50.0, 'bank', {'account_number': '1234567890', 'ifsc_code': 'HDFC0001234', 'account_holder_name': 'Test'})
        self.assertFalse(ok)
        self.assertIn("PAN", msg)

        # Invalid PAN format
        ok, msg = request_withdrawal('creator-1', 50.0, 'bank', {'pan_number': 'INVALID12', 'account_holder_name': 'Test', 'account_number': '1234567890', 'ifsc_code': 'HDFC0001234'})
        self.assertFalse(ok)
        self.assertIn("Invalid PAN", msg)

        # Missing Bank IFSC
        ok, msg = request_withdrawal('creator-1', 50.0, 'bank', {'pan_number': 'ABCDE1234F', 'account_holder_name': 'Test', 'account_number': '1234567890'})
        self.assertFalse(ok)
        self.assertIn("IFSC", msg)


if __name__ == '__main__':
    unittest.main()


