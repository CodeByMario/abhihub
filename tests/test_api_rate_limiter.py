import unittest

from methods.api_rate_limiter import check_api_rate_limit, clear_api_rate_limits


class ApiRateLimiterTests(unittest.TestCase):
    def setUp(self):
        clear_api_rate_limits()

    def tearDown(self):
        clear_api_rate_limits()

    def test_limits_requests_per_principal_in_window(self):
        self.assertEqual(
            check_api_rate_limit('user', 'user-1', max_requests=2, window_seconds=60, now=100),
            (True, 0),
        )
        self.assertEqual(
            check_api_rate_limit('user', 'user-1', max_requests=2, window_seconds=60, now=101),
            (True, 0),
        )
        allowed, retry_after = check_api_rate_limit(
            'user', 'user-1', max_requests=2, window_seconds=60, now=102
        )
        self.assertFalse(allowed)
        self.assertEqual(retry_after, 58)

    def test_separates_users_and_limit_kinds(self):
        self.assertEqual(
            check_api_rate_limit('user', 'user-1', max_requests=1, window_seconds=60, now=100),
            (True, 0),
        )
        self.assertEqual(
            check_api_rate_limit('user', 'user-2', max_requests=1, window_seconds=60, now=100),
            (True, 0),
        )
        self.assertEqual(
            check_api_rate_limit('ip', 'user-1', max_requests=1, window_seconds=60, now=100),
            (True, 0),
        )

    def test_expires_requests_at_window_boundary(self):
        self.assertEqual(
            check_api_rate_limit('user', 'user-1', max_requests=1, window_seconds=60, now=100),
            (True, 0),
        )
        self.assertEqual(
            check_api_rate_limit('user', 'user-1', max_requests=1, window_seconds=60, now=160),
            (True, 0),
        )


if __name__ == '__main__':
    unittest.main()
