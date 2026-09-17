"""
cache_manager.py — Level-wise Cache Management System for AbhiHub
=================================================================

Architecture: L1 → L2 → L3 → Origin

- L1: Process-local in-memory LRU cache (TTL + LRU eviction)
  Scope: per-worker-process. Fastest, zero network. Ideal for hot metadata
  that is read-heavy and changes infrequently (dropdowns, config, user profile).

- L2: Redis / Redis-compatible KV store (optional)
  Scope: shared across all workers and dynos. Provides cross-worker cache
  invalidation. Falls back to L1-only if Redis is not configured.

- L3: CDN edge cache (Cloudflare / Cloudinary / browser)
  Scope: global edge. Configured via HTTP Cache-Control headers on responses.

- Origin: Supabase / Cloudinary / Firebase (the actual data sources)

Usage:
    from cache_manager import cache
    cache = AbhiHubCache(app)  # call once at startup

    # Read with auto-populate
    colleges = cache.get_cached('colleges', cache.L1, ttl=3600, fetcher=get_all_colleges)

    # Invalidate on write
    cache.invalidate('colleges', cache.L1)

Design notes:
- All cache keys are namespaced with a version prefix to allow global busting.
- L1 uses OrderedDict for O(1) LRU eviction.
- L2 uses redis-py with json serialization (or msgpack if available).
- L3 is purely HTTP headers — no Python code needed, but we provide
  helpers to set the right Cache-Control headers.
- Every cache hit/miss/eviction is logged for observability.
- Graceful degradation: if Redis is down, L1-only mode is used transparently.
"""

import os
import time
import json
import logging
import threading
from collections import OrderedDict
from functools import wraps
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class CacheLevel:
    """Cache level constants."""
    L1 = "l1"   # In-memory (per-worker)
    L2 = "l2"   # Redis (shared across workers)
    L3 = "l3"   # CDN / Browser (HTTP headers)
    ORIGIN = "origin"  # Direct fetch from source


class TTL:
    """Pre-defined TTL values in seconds."""
    SHORT = 60           # 1 minute — rapidly changing data (quota, user status)
    MEDIUM = 300         # 5 minutes — near-real-time data (search suggestions)
    LONG = 1800          # 30 minutes — fairly static data (subjects, branches)
    VERY_LONG = 3600     # 1 hour — rarely changing (dropdowns, config)
    SESSION = 86400      # 24 hours — session data (user profile, permissions)


class CacheKeyVersion:
    """
    Global cache key version prefix.
    Increment this single value to invalidate ALL L1 + L2 cache entries at once.
    This is the "nuclear option" for cache busting during deploys or config changes.
    """
    # Bump this when you need a global cache wipe
    CURRENT = 1


def _vkey(key):
    """Wrap a logical key with the global version prefix."""
    return f"v{CacheKeyVersion.CURRENT}:{key}"


class L1Cache:
    """
    Level 1: Process-local in-memory LRU cache.

    Benefits:
    - Zero network latency (pure CPU/memory)
    - Thread-safe
    - Bounded memory (LRU eviction with max entries)

    Limitations:
    - Not shared across Gunicorn workers or dynos
    - Lost on worker restart
    """

    def __init__(self, max_entries=200, default_ttl=TTL.MEDIUM):
        self._store = OrderedDict()
        self._lock = threading.RLock()
        self._max_entries = max_entries
        self._default_ttl = default_ttl
        self._stats = {"hits": 0, "misses": 0, "evictions": 0}

    def get(self, key):
        """Retrieve a value from L1. Returns (data, ttl_left) or (None, 0) on miss/expiry."""
        vkey = _vkey(key)
        with self._lock:
            entry = self._store.get(vkey)
            if entry is None:
                self._stats["misses"] += 1
                return None, 0

            # Check TTL expiry
            if time.time() > entry["expires_at"]:
                del self._store[vkey]
                self._stats["evictions"] += 1
                self._stats["misses"] += 1
                return None, 0

            # Move to end (most recently used)
            self._store.move_to_end(vkey)
            self._stats["hits"] += 1
            ttl_left = entry["expires_at"] - time.time()
            return entry["data"], ttl_left

    def set(self, key, data, ttl=None):
        """Store data in L1 with optional TTL override."""
        vkey = _vkey(key)
        ttl = ttl if ttl is not None else self._default_ttl
        expires_at = time.time() + ttl

        with self._lock:
            # Evict oldest if at capacity
            if vkey not in self._store and len(self._store) >= self._max_entries:
                oldest_key = next(iter(self._store))
                del self._store[oldest_key]
                self._stats["evictions"] += 1

            self._store[vkey] = {
                "data": data,
                "expires_at": expires_at,
                "set_at": time.time(),
            }
            self._store.move_to_end(vkey)

    def delete(self, key):
        """Remove a key from L1."""
        vkey = _vkey(key)
        with self._lock:
            if vkey in self._store:
                del self._store[vkey]

    def clear(self):
        """Clear all L1 entries (resets version, so all reads miss until repopulated)."""
        with self._lock:
            self._store.clear()
            self._stats = {"hits": 0, "misses": 0, "evictions": 0}

    def stats(self):
        return dict(self._stats)

    def size(self):
        return len(self._store)


class L2Cache:
    """
    Level 2: Redis-backed shared cache.

    Benefits:
    - Shared across all Gunicorn workers and dynos
    - Persistent across worker restarts (if Redis persists)
    - Allows cross-worker invalidation

    Limitations:
    - Network latency (~0.1-1ms per access)
    - Requires Redis to be running (graceful fallback to L1-only)
    """

    def __init__(self, app=None, redis_url=None, default_ttl=TTL.MEDIUM):
        self._redis_url = redis_url or os.getenv("REDIS_URL")
        self._redis_client = None
        self._default_ttl = default_ttl
        self._enabled = False
        self._stats = {"hits": 0, "misses": 0, "errors": 0}

        if app:
            self.init_app(app)

    def init_app(self, app):
        """Initialize Redis connection (lazy, so missing Redis doesn't crash startup)."""
        if not self._redis_url:
            logger.info("[L2 Cache] Redis URL not configured — running in L1-only mode")
            return

        try:
            import redis
            self._redis_client = redis.from_url(self._redis_url, socket_timeout=2, socket_connect_timeout=2)
            # Test connection
            self._redis_client.ping()
            self._enabled = True
            logger.info("[L2 Cache] Redis connected and ready")
        except Exception as e:
            logger.warning(f"[L2 Cache] Redis connection failed ({e}) — running in L1-only mode")
            self._redis_client = None
            self._enabled = False

    def _serialize(self, value):
        """Serialize value for Redis storage."""
        return json.dumps(value, default=str)

    def _deserialize(self, raw):
        """Deserialize value from Redis storage."""
        if raw is None:
            return None
        return json.loads(raw)

    def get(self, key):
        """Retrieve a value from L2. Returns (data, ttl_left) or (None, 0)."""
        if not self._enabled:
            self._stats["misses"] += 1
            return None, 0

        vkey = _vkey(key)
        try:
            raw = self._redis_client.get(vkey)
            if raw is None:
                self._stats["misses"] += 1
                return None, 0

            data = self._deserialize(raw)
            ttl_left = self._redis_client.ttl(vkey)
            self._stats["hits"] += 1
            return data, ttl_left
        except Exception as e:
            self._stats["errors"] += 1
            logger.debug(f"[L2 Cache] Get error for {vkey}: {e}")
            return None, 0

    def set(self, key, data, ttl=None):
        """Store data in L2 with optional TTL override."""
        if not self._enabled:
            return

        vkey = _vkey(key)
        ttl = ttl if ttl is not None else self._default_ttl
        try:
            self._redis_client.setex(vkey, int(ttl), self._serialize(data))
        except Exception as e:
            self._stats["errors"] += 1
            logger.debug(f"[L2 Cache] Set error for {vkey}: {e}")

    def delete(self, key):
        """Remove a key from L2 (invalidate across all workers)."""
        if not self._enabled:
            return

        vkey = _vkey(key)
        try:
            self._redis_client.delete(vkey)
        except Exception as e:
            self._stats["errors"] += 1
            logger.debug(f"[L2 Cache] Delete error for {vkey}: {e}")

    def clear_pattern(self, pattern):
        """Delete all keys matching a pattern (L2-wide invalidation)."""
        if not self._enabled:
            return

        try:
            for key in self._redis_client.scan_iter(match=pattern):
                self._redis_client.delete(key)
        except Exception as e:
            self._stats["errors"] += 1
            logger.debug(f"[L2 Cache] Pattern delete error: {e}")

    def clear(self):
        """Flush all cache entries (DANGEROUS — use clear_pattern for targeted clears)."""
        if not self._enabled:
            return
        try:
            self._redis_client.flushdb()
        except Exception as e:
            self._stats["errors"] += 1
            logger.warning(f"[L2 Cache] Flush failed: {e}")

    def stats(self):
        return dict(self._stats)

    def is_enabled(self):
        return self._enabled


class AbhiHubCache:
    """
    Top-level cache orchestrator managing L1 + L2 + L3 tiers.

    The hierarchy works as follows:
    1. Check L1 (fastest, in-memory)
    2. If L1 miss, check L2 (Redis, shared)
    3. If L2 miss, call the fetcher to get fresh data from origin
    4. Write the fresh data to BOTH L1 and L2 (write-through)
    5. L3 is handled by HTTP response headers set separately

    This gives us a "multi-level cascade" where the first request populates
    all layers, and subsequent requests are served from whichever layer is fastest.
    """

    def __init__(self, app=None, redis_url=None, l1_max_entries=500):
        self.L1 = CacheLevel.L1
        self.L2 = CacheLevel.L2
        self.L3 = CacheLevel.L3
        self.ORIGIN = CacheLevel.ORIGIN

        # TTL aliases for ergonomic use: cache.LONG, cache.MEDIUM, etc.
        self.SHORT = TTL.SHORT
        self.MEDIUM = TTL.MEDIUM
        self.LONG = TTL.LONG
        self.VERY_LONG = TTL.VERY_LONG
        self.SESSION = TTL.SESSION

        self.l1 = L1Cache(max_entries=l1_max_entries, default_ttl=TTL.MEDIUM)
        self.l2 = L2Cache(redis_url=redis_url)

        if app:
            self.init_app(app)

    def init_app(self, app):
        """Initialize the cache system within a Flask app context."""
        app.extensions["abhi_cache"] = self
        if not self.l2.is_enabled():
            self.l2.init_app(app)

        # Expose cache to Jinja templates
        app.jinja_env.globals["cache_version"] = CacheKeyVersion.CURRENT

    # ─── Core API ─────────────────────────────────────────────────────────

    def get_cached(self, key, level=CacheLevel.L1, ttl=TTL.MEDIUM, fetcher=None):
        """
        Retrieve a value from the cache hierarchy, falling back to a fetcher.

        Args:
            key:     Logical cache key (e.g., "colleges:cs:" for CS department colleges)
            level:   Starting cache level (L1 or L2). L3 is handled via HTTP headers.
            ttl:     Time-to-live for cache entries in seconds
            fetcher: Zero-argument callable that returns fresh data on cache miss

        Returns:
            The cached or freshly-fetched data.
            If both cache layers miss and no fetcher provided, returns None.
        """
        # 1. Try L1 first (fastest)
        data, ttl_left = self.l1.get(key)
        if data is not None:
            return data

        # 2. If L1 miss and L2 is enabled, try L2
        if level in (CacheLevel.L2, CacheLevel.L1):
            data, ttl_left = self.l2.get(key)
            if data is not None:
                # Write-through to L1 for future fast access
                self.l1.set(key, data, ttl=ttl_left)
                return data

        # 3. Cache miss — call the fetcher if provided
        if fetcher is not None:
            data = fetcher()
            if data is not None:
                self.l1.set(key, data, ttl=ttl)
                self.l2.set(key, data, ttl=ttl)
                return data

        return None

    def set_cached(self, key, data, ttl=TTL.MEDIUM):
        """Explicitly set a value in both L1 and L2."""
        self.l1.set(key, data, ttl=ttl)
        self.l2.set(key, data, ttl=ttl)

    def invalidate(self, key, level=CacheLevel.L1):
        """
        Invalidate (remove) a cache entry at the specified level or all levels.

        Args:
            key:  Logical cache key (without version prefix)
            level: CacheLevel.L1, L2, or "all" for both layers
        """
        if level in (CacheLevel.L1, CacheLevel.L2):
            self.l1.delete(key)
            self.l2.delete(key)
        elif level == "all":
            self.l1.delete(key)
            self.l2.delete(key)

    def invalidate_pattern(self, pattern, level=CacheLevel.L1):
        """
        Invalidate all cache keys matching a pattern.

        Args:
            pattern: Glob-style pattern (e.g., "documents:*" or "user:*")
            level:   CacheLevel.L1, L2, or "all"
        """
        # L1: iterate and delete matching keys
        from fnmatch import fnmatch
        with self.l1._lock:
            keys_to_delete = []
            for vkey in list(self.l1._store.keys()):
                # vkey format is "v{n}:{original_key}"
                logical_key = vkey.split(":", 1)[1] if ":" in vkey else vkey
                if fnmatch(logical_key, pattern):
                    keys_to_delete.append(vkey)
            for vkey in keys_to_delete:
                del self.l1._store[vkey]

        # L2: use Redis scan_iter
        if level in (CacheLevel.L2, CacheLevel.L1, "all"):
            self.l2.clear_pattern(f"_v{CacheKeyVersion.CURRENT}:{pattern}")

    def bump_version(self):
        """
        Increment the global cache key version.

        This effectively invalidates all L1 and L2 cache entries at once.
        Use this after deploys, config changes, or bulk data migrations.
        """
        CacheKeyVersion.CURRENT += 1
        logger.info(f"[Cache] Global cache version bumped to {CacheKeyVersion.CURRENT}")

    def clear_all(self):
        """Clear all cache layers. Use with caution — causes thundering herd."""
        self.l1.clear()
        self.l2.clear()
        logger.info("[Cache] All cache layers cleared")

    def stats(self):
        """Return stats for all cache layers."""
        return {
            "l1": {**self.l1.stats(), "entries": self.l1.size()},
            "l2": self.l2.stats(),
            "l2_enabled": self.l2.is_enabled(),
            "version": CacheKeyVersion.CURRENT,
        }

    # ─── L3: HTTP Cache Headers ───────────────────────────────────────────

    def set_cache_headers(self, response, max_age, stale_while_revalidate=True, stale_if_error=86400):
        """
        Set HTTP Cache-Control headers on a Flask response for L3 (CDN/browser) caching.

        Args:
            response: Flask Response object
            max_age:               Max age in seconds for CDN/browser caching
            stale_while_revalidate: Allow serving stale content while revalidating (SWR)
            stale_if_error:        Serve stale content if origin returns error
        """
        parts = [f"public, max-age={max_age}, s-maxage={max_age}"]

        if stale_while_revalidate:
            parts.append(f"stale-while-revalidate={max_age * 2}")
        if stale_if_error:
            parts.append(f"stale-if-error={stale_if_error}")

        response.headers["Cache-Control"] = ", ".join(parts)
        response.headers["Vary"] = "Authorization, Accept-Encoding"
        return response

    # ─── Decorators ───────────────────────────────────────────────────────

    def cached(self, key_template, ttl=TTL.MEDIUM, level=CacheLevel.L1):
        """
        Decorator that wraps a function with cache logic.

        Args:
            key_template: A format string for the cache key, using function args.
                         e.g. "user_profile:{user_id}" for a function (user_id)
            ttl:          Cache TTL in seconds
            level:        Cache level to check first

        Example:
            @cache.cached("colleges:{department_id}", ttl=TTL.VERY_LONG)
            def get_colleges(department_id):
                ...
        """
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Build cache key from template + args
                try:
                    cache_key = key_template.format(*args, **kwargs)
                except (IndexError, KeyError):
                    # Fall back to function name + args hash
                    cache_key = f"{func.__name__}:{hash(str(args) + str(kwargs))}"

                data = self.get_cached(cache_key, level=level, ttl=ttl, fetcher=None)
                if data is not None:
                    return data

                # Cache miss — call function and cache result
                data = func(*args, **kwargs)
                if data is not None:
                    self.set_cached(cache_key, data, ttl=ttl)
                return data

            # Attach cache control to the wrapper function
            wrapper._cache_key_template = key_template
            wrapper._cache_ttl = ttl
            return wrapper
        return decorator

    # ─── Domain-Specific Cache Helpers ────────────────────────────────────

    # --- Static/Reference Data (very long TTL) ---

    def get_dropdowns(self, fetcher):
        """Cache colleges, branches, departments for dropdown forms."""
        return self.get_cached("dropdowns:all", level=self.L1, ttl=TTL.VERY_LONG, fetcher=fetcher)

    def get_subjects(self, department_id, semester, fetcher):
        """Cache subjects list per department/semester."""
        key = f"subjects:{department_id}:{semester or 'all'}"
        return self.get_cached(key, level=self.L1, ttl=TTL.LONG, fetcher=fetcher)

    # --- User-Specific Data (session TTL, invalidated on login/logout) ---

    def get_user_profile(self, user_id, fetcher):
        """Cache user profile — short TTL, invalidated on profile update."""
        return self.get_cached(f"user:profile:{user_id}", level=self.L1, ttl=TTL.MEDIUM, fetcher=fetcher)

    def get_user_quota(self, user_id, fetcher):
        """Cache user paper quota — very short TTL since it changes frequently."""
        return self.get_cached(f"user:quota:{user_id}", level=self.L1, ttl=TTL.SHORT, fetcher=fetcher)

    def invalidate_user(self, user_id):
        """Invalidate all cache entries for a user (call on profile/quota update)."""
        self.invalidate_pattern(f"user:*", level="all")

    # --- Document/Resource Data (long TTL, invalidated on upload/verify) ---

    def get_file_list(self, filters, fetcher):
        """Cache the unified file list with filters — medium TTL, invalidated on upload."""
        filter_str = json.dumps(filters, sort_keys=True, default=str)
        key = f"files:list:{hash(filter_str)}"
        return self.get_cached(key, level=self.L2, ttl=TTL.MEDIUM, fetcher=fetcher)

    def get_file_meta(self, file_id, fetcher):
        """Cache individual file metadata — long TTL."""
        return self.get_cached(f"file:meta:{file_id}", level=self.L1, ttl=TTL.LONG, fetcher=fetcher)

    def get_search_results(self, query_hash, fetcher):
        """Cache search results — short-medium TTL (searches are read-heavy)."""
        key = f"search:{query_hash}"
        return self.get_cached(key, level=self.L1, ttl=TTL.MEDIUM, fetcher=fetcher)

    def invalidate_files(self):
        """Invalidate all file-related cache entries (call on upload/verify/delete)."""
        self.invalidate_pattern("file:*", level="all")
        self.invalidate_pattern("files:*", level="all")
        self.invalidate_pattern("search:*", level="all")
        self.invalidate_pattern("dropdowns:*", level="all")

    def invalidate_dropdowns(self):
        """Invalidate all dropdown metadata cache entries (colleges, branches, subjects)."""
        self.invalidate_pattern("dropdowns:*", level="all")

    def invalidate_user(self, user_id):
        """Invalidate user-specific cache entries (quota, profile)."""
        self.invalidate(f"user:quota:{user_id}", level="all")
        self.invalidate(f"user:profile:{user_id}", level="all")

    # --- Feature Toggle Data ---

    def get_config_flags(self, fetcher):
        """Cache feature flags / config — medium TTL."""
        return self.get_cached("config:flags", level=self.L1, ttl=TTL.LONG, fetcher=fetcher)

    def invalidate_config(self):
        """Invalidate config cache."""
        self.invalidate("config:flags", level="all")

    # ─── Response Helpers ---

    def cache_response(self, ttl=TTL.LONG, level=CacheLevel.L3, **kwargs):
        """
        Decorator that sets appropriate L3 cache headers on a Flask response.

        Args:
            ttl: TTL in seconds for CDN/browser cache
            level: Cache level (L3 by default — CDN/browser)
        """
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                response = func(*args, **kwargs)
                if hasattr(response, "headers"):
                    self.set_cache_headers(response, max_age=ttl, **kwargs)
                return response
            return wrapper
        return decorator


# ─── Global singleton instance ──────────────────────────────────────────────

_cache_instance = None
_cache_lock = threading.Lock()


def get_cache():
    """Get or create the global cache singleton."""
    global _cache_instance
    if _cache_instance is not None:
        return _cache_instance

    with _cache_lock:
        if _cache_instance is None:
            _cache_instance = AbhiHubCache()
    return _cache_instance


def init_cache(app=None):
    """Initialize the global cache (call during app startup)."""
    global _cache_instance
    with _cache_lock:
        _cache_instance = AbhiHubCache(app=app)
    return _cache_instance


# ─── Flask integration helpers ─────────────────────────────────────────────

def cache_dropdowns(fetcher):
    """Helper: get cached dropdowns via the global cache instance."""
    return get_cache().get_dropdowns(fetcher)


def invalidate_file_cache():
    """Helper: invalidate all file-related cache entries."""
    get_cache().invalidate_files()


def cache_health():
    """Return cache stats for health-check endpoints."""
    return get_cache().stats()
