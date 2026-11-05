"""
Patch cache_manager.py with observability metrics integration.
"""
import os

path = 'cache_manager.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

target = """            # Move to end (most recently used)
            self._store.move_to_end(vkey)
            self._stats["hits"] += 1
            ttl_left = entry["expires_at"] - time.time()
            return entry["data"], ttl_left"""

replacement = """            # Move to end (most recently used)
            self._store.move_to_end(vkey)
            self._stats["hits"] += 1
            try:
                from observability.metrics import record_cache_event
                record_cache_event("CACHE_HIT", level="l1", key=key)
            except Exception:
                pass
            ttl_left = entry["expires_at"] - time.time()
            return entry["data"], ttl_left"""

if target in content:
    content = content.replace(target, replacement, 1)

target_miss = """            if entry is None:
                self._stats["misses"] += 1
                return None, 0"""

replacement_miss = """            if entry is None:
                self._stats["misses"] += 1
                try:
                    from observability.metrics import record_cache_event
                    record_cache_event("CACHE_MISS", level="l1", key=key)
                except Exception:
                    pass
                return None, 0"""

if target_miss in content:
    content = content.replace(target_miss, replacement_miss, 1)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Patched cache_manager.py with metrics")
