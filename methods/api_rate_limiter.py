"""Process-local API request limiter with bounded, thread-safe sliding windows.

The Flask request hook uses this as a protective default. Multi-instance deployments
should replace the store with an atomic shared backend such as Redis.
"""
from __future__ import annotations

import hashlib
import math
import threading
import time
from collections import OrderedDict, deque

_MAX_BUCKETS = 20_000
_BUCKETS: OrderedDict[str, deque[float]] = OrderedDict()
_LOCK = threading.RLock()


def _bucket_id(kind: str, principal: str) -> str:
    value = f"{kind}:{principal}".encode("utf-8", errors="replace")
    return hashlib.sha256(value).hexdigest()


def check_api_rate_limit(
    kind: str,
    principal: str,
    *,
    max_requests: int,
    window_seconds: int,
    now: float | None = None,
) -> tuple[bool, int]:
    """Atomically admit a request and return ``(allowed, retry_after_seconds)``."""
    if max_requests < 1 or window_seconds < 1 or not principal:
        raise ValueError("A principal and positive rate-limit values are required")

    current = time.monotonic() if now is None else now
    key = _bucket_id(kind, principal)
    cutoff = current - window_seconds

    with _LOCK:
        timestamps = _BUCKETS.get(key)
        if timestamps is None:
            if len(_BUCKETS) >= _MAX_BUCKETS:
                # Drop expired entries first; cap memory if high-cardinality traffic
                # still exceeds the configured bound.
                expired_keys = [
                    bucket_key
                    for bucket_key, bucket_times in _BUCKETS.items()
                    if not bucket_times or bucket_times[-1] <= cutoff
                ]
                for bucket_key in expired_keys:
                    _BUCKETS.pop(bucket_key, None)
                while len(_BUCKETS) >= _MAX_BUCKETS:
                    _BUCKETS.popitem(last=False)
            timestamps = deque()
            _BUCKETS[key] = timestamps

        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()

        _BUCKETS.move_to_end(key)
        if len(timestamps) >= max_requests:
            retry_after = max(1, math.ceil(timestamps[0] + window_seconds - current))
            return False, retry_after

        timestamps.append(current)
        return True, 0


def clear_api_rate_limits() -> None:
    """Clear in-memory state; intended for isolated tests and process shutdown."""
    with _LOCK:
        _BUCKETS.clear()
