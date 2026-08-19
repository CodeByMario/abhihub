"""
pytest bootstrap for the AbhiHub test suite.

Puts the repository root on sys.path so `from app import app` works no
matter where pytest is invoked from (repo root, tests/, or an IDE).

Also supplies safe dummy values for the env vars that app.py requires at
import time, so importing the app in a test never needs real credentials.
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Minimal env so `import app` succeeds without real secrets.
os.environ.setdefault("SECRET_KEY", "test-only-not-a-real-secret")
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("ADMIN_EMAILS", "")
