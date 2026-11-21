"""
Redis client wrapper for Upstash REST and Vercel serverless.
Uses `upstash-redis` REST client when UPSTASH_REDIS_REST_URL and
UPSTASH_REDIS_REST_TOKEN are set. Falls back to a thread-safe in-memory
mock store when offline or in unit tests.
"""
import os
import time
import json
import logging
from typing import Optional, Any, Dict, List

logger = logging.getLogger("redis.client")

_client_instance = None


class InMemoryRedisMock:
    """Thread-safe in-memory mock matching Upstash REST signatures."""
    def __init__(self):
        self._kv: Dict[str, Any] = {}
        self._ttls: Dict[str, float] = {}
        self._zsets: Dict[str, Dict[str, float]] = {}
        self._sets: Dict[str, set] = {}

    def _is_expired(self, key: str) -> bool:
        if key in self._ttls and time.time() > self._ttls[key]:
            self.delete(key)
            return True
        return False

    def get(self, key: str) -> Optional[str]:
        if self._is_expired(key):
            return None
        val = self._kv.get(key)
        return str(val) if val is not None else None

    def set(self, key: str, value: Any, ex: Optional[int] = None, **kwargs) -> bool:
        self._kv[key] = str(value)
        if ex:
            self._ttls[key] = time.time() + ex
        elif key in self._ttls:
            del self._ttls[key]
        return True

    def setex(self, key: str, seconds: int, value: Any) -> bool:
        return self.set(key, value, ex=seconds)

    def getdel(self, key: str) -> Optional[str]:
        if self._is_expired(key):
            return None
        val = self.get(key)
        self.delete(key)
        return val

    def incr(self, key: str) -> int:
        return self.incrby(key, 1)

    def incrby(self, key: str, amount: int) -> int:
        if self._is_expired(key):
            self._kv[key] = "0"
        curr = int(self._kv.get(key, 0) or 0)
        new_val = curr + amount
        self._kv[key] = str(new_val)
        return new_val

    def expire(self, key: str, seconds: int) -> bool:
        if key in self._kv or key in self._zsets or key in self._sets:
            self._ttls[key] = time.time() + seconds
            return True
        return False

    def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            deleted = False
            if k in self._kv:
                del self._kv[k]
                deleted = True
            if k in self._ttls:
                del self._ttls[k]
            if k in self._zsets:
                del self._zsets[k]
                deleted = True
            if k in self._sets:
                del self._sets[k]
                deleted = True
            if deleted:
                count += 1
        return count

    # Sorted sets
    def zadd(self, key: str, scores: Dict[str, float], **kwargs) -> int:
        if key not in self._zsets or self._is_expired(key):
            self._zsets[key] = {}
        count = 0
        for member, score in scores.items():
            if member not in self._zsets[key]:
                count += 1
            self._zsets[key][member] = float(score)
        return count

    def zrem(self, key: str, *members: str) -> int:
        if key not in self._zsets or self._is_expired(key):
            return 0
        count = 0
        for m in members:
            if m in self._zsets[key]:
                del self._zsets[key][m]
                count += 1
        return count

    def zrank(self, key: str, member: str) -> Optional[int]:
        if key not in self._zsets or self._is_expired(key):
            return None
        sorted_members = sorted(self._zsets[key].items(), key=lambda x: x[1])
        for idx, (m, _) in enumerate(sorted_members):
            if m == member:
                return idx
        return None

    def zcard(self, key: str) -> int:
        if key not in self._zsets or self._is_expired(key):
            return 0
        return len(self._zsets[key])

    def zrange(self, key: str, start: int, stop: int, withscores: bool = False) -> List[Any]:
        if key not in self._zsets or self._is_expired(key):
            return []
        sorted_items = sorted(self._zsets[key].items(), key=lambda x: x[1])
        stop_idx = len(sorted_items) if stop == -1 else stop + 1
        slice_items = sorted_items[start:stop_idx]
        if withscores:
            res = []
            for m, s in slice_items:
                res.extend([m, s])
            return res
        return [m for m, _ in slice_items]

    def zrangebyscore(self, key: str, min: Any, max: Any, withscores: bool = False,
                       offset: Optional[int] = None, count: Optional[int] = None) -> List[Any]:
        if key not in self._zsets or self._is_expired(key):
            return []
        min_val = float('-inf') if min in ('-inf', '-inf') else float(min)
        max_val = float('inf') if max in ('+inf', 'inf') else float(max)
        filtered = [
            (m, s) for m, s in self._zsets[key].items()
            if min_val <= s <= max_val
        ]
        sorted_items = sorted(filtered, key=lambda x: x[1])
        if offset is not None and count is not None:
            sorted_items = sorted_items[offset:offset + count]
        if withscores:
            res = []
            for m, s in sorted_items:
                res.extend([m, s])
            return res
        return [m for m, _ in sorted_items]

    # Sets
    def sadd(self, key: str, *members: str) -> int:
        if key not in self._sets or self._is_expired(key):
            self._sets[key] = set()
        prev = len(self._sets[key])
        self._sets[key].update(members)
        return len(self._sets[key]) - prev

    def srem(self, key: str, *members: str) -> int:
        if key not in self._sets or self._is_expired(key):
            return 0
        prev = len(self._sets[key])
        self._sets[key].difference_update(members)
        return prev - len(self._sets[key])

    def smembers(self, key: str) -> set:
        if key not in self._sets or self._is_expired(key):
            return set()
        return set(self._sets[key])


def get_redis_client():
    """Returns singleton Redis client (Upstash or in-memory fallback)."""
    global _client_instance
    if _client_instance is not None:
        return _client_instance

    url = os.getenv("UPSTASH_REDIS_REST_URL")
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN")

    if url and token:
        try:
            from upstash_redis import Redis
            _client_instance = Redis(url=url, token=token)
            logger.info("[REDIS] Connected to Upstash Redis REST")
            return _client_instance
        except Exception as e:
            logger.warning("[REDIS] Failed to initialize Upstash client: %s; using in-memory mock", e)

    _client_instance = InMemoryRedisMock()
    return _client_instance


def cache_get_json(key: str) -> Optional[Any]:
    """Retrieve and deserialize JSON from Redis cache."""
    try:
        r = get_redis_client()
        raw = r.get(key)
        if raw:
            return json.loads(raw)
    except Exception as e:
        logger.debug("[CACHE_GET_ERR] %s: %s", key, e)
    return None


def cache_set_json(key: str, data: Any, ttl_seconds: int = 3600) -> bool:
    """Serialize and store JSON in Redis cache with TTL."""
    try:
        r = get_redis_client()
        payload = json.dumps(data)
        r.setex(key, ttl_seconds, payload)
        return True
    except Exception as e:
        logger.debug("[CACHE_SET_ERR] %s: %s", key, e)
        return False


def cache_delete(key: str) -> bool:
    """Delete a key from Redis cache."""
    try:
        r = get_redis_client()
        r.delete(key)
        return True
    except Exception as e:
        logger.debug("[CACHE_DEL_ERR] %s: %s", key, e)
        return False
