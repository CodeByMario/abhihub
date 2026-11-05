"""
Remove local import os inside get_ad_decision.
"""
with open('methods/scoring_engine.py', 'r', encoding='utf-8') as f:
    content = f.read()

target = """        # Check L1 cache to avoid redundant Supabase queries on every navigation (bypass during pytest runs)
        user_metrics = None
        cache = None
        try:
            import os
            is_testing = bool(os.environ.get('PYTEST_CURRENT_TEST'))"""

replacement = """        # Check L1 cache to avoid redundant Supabase queries on every navigation (bypass during pytest runs)
        user_metrics = None
        cache = None
        try:
            is_testing = bool(os.environ.get('PYTEST_CURRENT_TEST'))"""

if target in content:
    content = content.replace(target, replacement, 1)
    with open('methods/scoring_engine.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed unbound local os in methods/scoring_engine.py")
else:
    print("Target not found")
