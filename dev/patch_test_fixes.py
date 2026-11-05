"""
Patch routes/app_pages.py, tests/test_delete_account_form.py, and methods/scoring_engine.py.
"""
import os

# 1. routes/app_pages.py: ensure @auth_required is present
pages_path = os.path.join('routes', 'app_pages.py')
with open(pages_path, 'r', encoding='utf-8') as f:
    content = f.read()

target = """@app_pages_bp.route('/delete-account', methods=['GET', 'POST'])
def delete_account():"""

replacement = """@app_pages_bp.route('/delete-account', methods=['GET', 'POST'])
@auth_required
def delete_account():"""

if target in content:
    content = content.replace(target, replacement, 1)
    with open(pages_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patched @auth_required in routes/app_pages.py")

# 2. tests/test_delete_account_form.py: add session user in setUp
test_path = os.path.join('tests', 'test_delete_account_form.py')
with open(test_path, 'r', encoding='utf-8') as f:
    t_content = f.read()

target_t = """        self.client = app.test_client()
        self.request_file = 'data/account_deletion_requests.json'"""

replacement_t = """        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess['user'] = {'uid': 'u-jane', 'email': 'jane@example.com'}
        self.request_file = 'data/account_deletion_requests.json'"""

if target_t in t_content:
    t_content = t_content.replace(target_t, replacement_t, 1)
    with open(test_path, 'w', encoding='utf-8') as f:
        f.write(t_content)
    print("Patched session user in tests/test_delete_account_form.py")

# 3. methods/scoring_engine.py: bypass L1 cache when current_app.testing is True
score_path = os.path.join('methods', 'scoring_engine.py')
with open(score_path, 'r', encoding='utf-8') as f:
    s_content = f.read()

target_s = """        # Check L1 cache to avoid redundant Supabase queries on every navigation
        user_metrics = None
        cache = None
        try:
            from cache_manager import get_cache
            cache = get_cache()
            user_metrics, _ = cache.l1.get(f\"user_ad_metrics:{user_id}\")
        except Exception:
            cache = None"""

replacement_s = """        # Check L1 cache to avoid redundant Supabase queries on every navigation (bypass in test suite)
        user_metrics = None
        cache = None
        try:
            from flask import has_app_context, current_app
            is_testing = current_app.config.get('TESTING', False) if has_app_context() else False
            if not is_testing:
                from cache_manager import get_cache
                cache = get_cache()
                user_metrics, _ = cache.l1.get(f\"user_ad_metrics:{user_id}\")
        except Exception:
            cache = None"""

if target_s in s_content:
    s_content = s_content.replace(target_s, replacement_s, 1)
    with open(score_path, 'w', encoding='utf-8') as f:
        f.write(s_content)
    print("Patched test bypass in methods/scoring_engine.py")
