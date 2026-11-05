"""
Patch methods/scoring_engine.py to check os.environ.get('PYTEST_CURRENT_TEST').
"""
import os

score_path = os.path.join('methods', 'scoring_engine.py')
with open(score_path, 'r', encoding='utf-8') as f:
    s_content = f.read()

target_s = """        # Check L1 cache to avoid redundant Supabase queries on every navigation (bypass in test suite)
        user_metrics = None
        cache = None
        try:
            from flask import has_app_context, current_app
            is_testing = current_app.config.get('TESTING', False) if has_app_context() else False
            if not is_testing:
                from cache_manager import get_cache
                cache = get_cache()
                user_metrics, _ = cache.l1.get(f"user_ad_metrics:{user_id}")
        except Exception:
            cache = None"""

replacement_s = """        # Check L1 cache to avoid redundant Supabase queries on every navigation (bypass during pytest runs)
        user_metrics = None
        cache = None
        try:
            import os
            is_testing = bool(os.environ.get('PYTEST_CURRENT_TEST'))
            if not is_testing:
                from cache_manager import get_cache
                cache = get_cache()
                user_metrics, _ = cache.l1.get(f"user_ad_metrics:{user_id}")
        except Exception:
            cache = None"""

if target_s in s_content:
    s_content = s_content.replace(target_s, replacement_s, 1)
    with open(score_path, 'w', encoding='utf-8') as f:
        f.write(s_content)
    print("Patched PYTEST_CURRENT_TEST check in methods/scoring_engine.py")
else:
    print("Target not found in methods/scoring_engine.py")
