"""
test_cache_manager.py — Tests for the Level-wise Cache Management System.

Run: pytest test_cache_manager.py -v
"""

import pytest
import time
import threading
from cache_manager import (
    AbhiHubCache, CacheLevel, TTL, CacheKeyVersion,
    L1Cache, L2Cache, _vkey
)


# ─── L1Cache unit tests ───────────────────────────────────────────────────

class TestL1Cache:
    def setup_method(self):
        self.cache = L1Cache(max_entries=5, default_ttl=TTL.SHORT)

    def test_set_and_get(self):
        """L1: set then get returns stored value."""
        self.cache.set("key1", {"data": "value1"}, ttl=10)
        data, ttl_left = self.cache.get("key1")
        assert data == {"data": "value1"}
        assert ttl_left > 0

    def test_miss_on_unset_key(self):
        """L1: get on unset key returns None."""
        data, _ = self.cache.get("nonexistent")
        assert data is None

    def test_ttl_expiry(self):
        """L1: entries expire after TTL."""
        self.cache.set("temp_key", "temp_value", ttl=1)
        data, _ = self.cache.get("temp_key")
        assert data == "temp_value"

        time.sleep(1.5)
        data, _ = self.cache.get("temp_key")
        assert data is None

    def test_lru_eviction(self):
        """L1: oldest entries evicted when max_entries exceeded."""
        for i in range(5):
            self.cache.set(f"k{i}", f"v{i}", ttl=10)

        # Access k0 to mark it as recently used
        self.cache.get("k0")

        # Add one more — should evict k1 (least recently used)
        self.cache.set("k5", "v5", ttl=10)

        data, _ = self.cache.get("k1")
        assert data is None  # evicted

        data, _ = self.cache.get("k0")
        assert data == "v0"  # survived — was accessed

    def test_delete(self):
        """L1: delete removes entry."""
        self.cache.set("del_key", "del_value", ttl=10)
        self.cache.delete("del_key")
        data, _ = self.cache.get("del_key")
        assert data is None

    def test_clear(self):
        """L1: clear empties the store."""
        self.cache.set("k1", "v1", ttl=10)
        self.cache.set("k2", "v2", ttl=10)
        self.cache.clear()
        assert self.cache.size() == 0

    def test_stats(self):
        """L1: stats track hits, misses, evictions."""
        self.cache.set("hit_key", "hit_val", ttl=10)
        self.cache.get("hit_key")   # hit
        self.cache.get("miss_key")  # miss
        stats = self.cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["evictions"] == 0

    def test_thread_safety(self):
        """L1: concurrent reads/writes don't crash."""
        results = []
        errors = []

        def worker(n):
            try:
                for i in range(100):
                    self.cache.set(f"thread_key_{n}_{i}", i, ttl=5)
                    self.cache.get(f"thread_key_{n}_{i}")
                results.append(True)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 5


# ─── L2Cache unit tests ───────────────────────────────────────────────────

class TestL2Cache:
    def setup_method(self):
        """L2 cache without Redis — should be disabled but not crash."""
        self.cache = L2Cache(redis_url=None)

    def test_disabled_without_redis(self):
        """L2: not enabled without Redis URL."""
        assert self.cache.is_enabled() is False

    def test_get_returns_none_when_disabled(self):
        """L2: get returns (None, 0) when disabled."""
        data, ttl = self.cache.get("any_key")
        assert data is None
        assert ttl == 0

    def test_set_noop_when_disabled(self):
        """L2: set is a no-op when disabled."""
        self.cache.set("test", "value")  # should not raise

    def test_delete_noop_when_disabled(self):
        """L2: delete is a no-op when disabled."""
        self.cache.delete("test")  # should not raise


# ─── AbhiHubCache integration tests ───────────────────────────────────────

class TestAbhiHubCache:
    def setup_method(self):
        self.cache = AbhiHubCache()

    def test_get_cached_miss_with_fetcher(self):
        """Cache: get_cached with no prior entry calls fetcher."""
        call_count = [0]

        def my_fetcher():
            call_count[0] += 1
            return {"items": [1, 2, 3]}

        result = self.cache.get_cached("test:key1", level=CacheLevel.L1, ttl=10, fetcher=my_fetcher)
        assert result == {"items": [1, 2, 3]}
        assert call_count[0] == 1

    def test_get_cached_hit_from_l1(self):
        """Cache: second call returns L1 hit, not calling fetcher again."""
        call_count = [0]

        def my_fetcher():
            call_count[0] += 1
            return {"items": [1, 2, 3]}

        # First call — miss, fetcher called
        result1 = self.cache.get_cached("test:key2", level=CacheLevel.L1, ttl=10, fetcher=my_fetcher)
        assert result1 == {"items": [1, 2, 3]}
        assert call_count[0] == 1

        # Second call — hit from L1, fetcher NOT called
        result2 = self.cache.get_cached("test:key2", level=CacheLevel.L1, ttl=10, fetcher=my_fetcher)
        assert result2 == {"items": [1, 2, 3]}
        assert call_count[0] == 1  # still 1 — no second fetch

    def test_get_cached_no_fetcher_returns_none(self):
        """Cache: get_cached with no fetcher and no entry returns None."""
        result = self.cache.get_cached("test:nonexistent", level=CacheLevel.L1, ttl=10, fetcher=None)
        assert result is None

    def test_set_cached(self):
        """Cache: set_cached stores in both layers."""
        self.cache.set_cached("test:set1", {"val": 42}, ttl=10)
        result = self.cache.get_cached("test:set1", level=CacheLevel.L1, ttl=10, fetcher=None)
        assert result == {"val": 42}

    def test_invalidate(self):
        """Cache: invalidate removes entry from L1."""
        self.cache.set_cached("test:invalidate1", "data", ttl=10)
        self.cache.invalidate("test:invalidate1", level="all")
        result = self.cache.get_cached("test:invalidate1", level=CacheLevel.L1, ttl=10, fetcher=None)
        assert result is None

    def test_invalidate_pattern(self):
        """Cache: invalidate_pattern removes all matching keys."""
        self.cache.set_cached("test:prefix:1", "a", ttl=10)
        self.cache.set_cached("test:prefix:2", "b", ttl=10)
        self.cache.set_cached("test:other:1", "c", ttl=10)

        self.cache.invalidate_pattern("test:prefix:*", level="all")

        result1 = self.cache.get_cached("test:prefix:1", level=CacheLevel.L1, ttl=10, fetcher=None)
        result2 = self.cache.get_cached("test:prefix:2", level=CacheLevel.L1, ttl=10, fetcher=None)
        assert result1 is None
        assert result2 is None

    def test_bump_version(self):
        """Cache: bump_version invalidates all keys (version prefix changes)."""
        self.cache.set_cached("test:versioning", "value", ttl=10)
        old_version = CacheKeyVersion.CURRENT

        self.cache.bump_version()
        assert CacheKeyVersion.CURRENT == old_version + 1

        # Old key should not be found after version bump
        result = self.cache.get_cached("test:versioning", level=CacheLevel.L1, ttl=10, fetcher=None)
        assert result is None

    def test_l1_l2_cascade(self):
        """Cache: L2 miss falls back to fetcher, L1 serves subsequent reads."""
        call_count = [0]

        def my_fetcher():
            call_count[0] += 1
            return {"fetched": True}

        # First call — L1 miss, L2 miss (disabled), fetcher called
        result1 = self.cache.get_cached("cascade:key", level=CacheLevel.L2, ttl=10, fetcher=my_fetcher)
        assert result1 == {"fetched": True}
        assert call_count[0] == 1

        # Second call — L1 hit
        result2 = self.cache.get_cached("cascade:key", level=CacheLevel.L2, ttl=10, fetcher=my_fetcher)
        assert result2 == {"fetched": True}
        assert call_count[0] == 1  # no second fetch

    def test_stats(self):
        """Cache: stats returns dict with l1, l2, version keys."""
        stats = self.cache.stats()
        assert "l1" in stats
        assert "l2" in stats
        assert "version" in stats
        assert "l2_enabled" in stats

    def test_clear_all(self):
        """Cache: clear_all empties everything."""
        self.cache.set_cached("clear:test1", "v1", ttl=10)
        self.cache.set_cached("clear:test2", "v2", ttl=10)
        self.cache.clear_all()
        assert self.cache.l1.size() == 0

    def test_domain_helper_dropdowns(self):
        """Cache: domain helper get_* methods work."""
        def fetch_subjects():
            return ["Math", "Physics"]

        result = self.cache.get_subjects("cs_dept", 3, fetch_subjects)
        assert result == ["Math", "Physics"]

    def test_domain_helper_quota(self):
        """Cache: user quota caching via domain helper."""
        def fetch_quota():
            return {"credits": 15, "total_views": 4}

        result = self.cache.get_user_quota("uid_123", fetch_quota)
        assert result == {"credits": 15, "total_views": 4}


# ─── TTL constants ─────────────────────────────────────────────────────────

class TestTTL:
    def test_ttl_values(self):
        """TTL: predefined constants have expected values."""
        assert TTL.SHORT == 60
        assert TTL.MEDIUM == 300
        assert TTL.LONG == 1800
        assert TTL.VERY_LONG == 3600
        assert TTL.SESSION == 86400


class TestCacheKeyVersion:
    def test_vkey_format(self):
        """Key versioning: _vkey prepends version prefix."""
        CacheKeyVersion.CURRENT = 5
        result = _vkey("mykey")
        assert result == "v5:mykey"
        CacheKeyVersion.CURRENT = 1  # reset


# ─── set_cache_headers tests (using Flask test client) ─────────────────────

class TestCacheHeaders:
    """
    Tests for HTTP cache headers (L3 — CDN/browser caching).
    Uses Flask test client for integration testing.
    """

    def test_health_endpoint_exists(self, app, client):
        """The /api/cache-health endpoint returns cache stats."""
        response = client.get('/api/cache-health')
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'ok'
        assert 'cache' in data

    def test_quota_endpoint_has_cache_headers(self, app, client):
        """The /api/quota endpoint sets Cache-Control headers."""
        # Need to be authenticated — skip if not possible
        response = client.get('/api/quota')
        # Should either return 200 (authenticated) or 401 (not authenticated)
        assert response.status_code in (200, 401)
        if response.status_code == 200:
            assert 'Cache-Control' in response.headers

    def test_colleges_endpoint_has_cache_headers(self, app, client):
        """The /api/colleges endpoint sets Cache-Control headers for CDN."""
        response = client.get('/api/colleges')
        assert response.status_code == 200
        assert 'Cache-Control' in response.headers
        cc = response.headers['Cache-Control']
        assert 'max-age=1800' in cc
        assert 'stale-while-revalidate' in cc

    def test_branches_endpoint_has_cache_headers(self, app, client):
        """The /api/branches endpoint sets Cache-Control headers for CDN."""
        response = client.get('/api/branches')
        assert response.status_code == 200
        assert 'Cache-Control' in response.headers
        cc = response.headers['Cache-Control']
        assert 'max-age=1800' in cc

    def test_subjects_endpoint_has_cache_headers(self, app, client):
        """The /api/subjects endpoint sets Cache-Control headers."""
        response = client.get('/api/subjects?department_id=test')
        assert response.status_code in (200, 400)
        if response.status_code == 200:
            assert 'Cache-Control' in response.headers


# ─── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def app():
    """Minimal Flask app for testing."""
    from flask import Flask, jsonify
    from cache_manager import AbhiHubCache

    test_app = Flask(__name__)
    test_app.config['TESTING'] = True
    cache = AbhiHubCache(test_app)

    @test_app.route('/api/cache-health')
    def health():
        return jsonify({'status': 'ok', 'cache': cache.stats()})

    @test_app.route('/api/quota')
    def quota():
        response = jsonify({'credits': 19, 'total_views': 0, 'quota_per_upload': 19})
        cache.set_cache_headers(response, max_age=60, stale_while_revalidate=True)
        return response

    @test_app.route('/api/colleges')
    def colleges():
        response = jsonify({'success': True, 'colleges': [{'id': '1', 'name': 'GHRCE'}]})
        cache.set_cache_headers(response, max_age=1800, stale_while_revalidate=True)
        return response

    @test_app.route('/api/branches')
    def branches():
        response = jsonify({'success': True, 'branches': [{'id': 'cs', 'name': 'Computer Science'}]})
        cache.set_cache_headers(response, max_age=1800, stale_while_revalidate=True)
        return response

    @test_app.route('/api/subjects')
    def subjects():
        from flask import request as req
        dept = req.args.get('department_id')
        if not dept:
            return jsonify({'success': False, 'subjects': [], 'message': 'department_id required'}), 400
        response = jsonify({'success': True, 'subjects': [{'id': '1', 'name': 'Maths'}]})
        cache.set_cache_headers(response, max_age=1800, stale_while_revalidate=True)
        return response

    return test_app


@pytest.fixture
def client(app):
    return app.test_client()
