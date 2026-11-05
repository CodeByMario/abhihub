"""
Test Search Vocabulary resolution for Phase 1 verification:
UITL201, ML, UHV, and GHRCE.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from methods.supabase_helper import init_supabase, init_supabase_admin


def test_vocab_lookup():
    client = init_supabase_admin() or init_supabase()
    if not client:
        pytest.skip("Supabase client not configured or unavailable")

    targets = ['uitl201', 'ml', 'uhv', 'ghrce']
    all_passed = True
    network_error = False

    print("\n--- Verifying Phase 1 Search Vocab ---")
    for term in targets:
        try:
            res = client.table('search_vocab').select('*').ilike('term', term).execute()
            rows = res.data or []
            if rows:
                print(f"[PASS] Vocab term '{term}' resolved to {len(rows)} record(s): {rows[0].get('label')} ({rows[0].get('kind')})")
            else:
                print(f"[NOTE] Vocab term '{term}' not found in DB table yet (Run migration & seed script).")
                all_passed = False
        except Exception as e:
            err_msg = str(e)
            print(f"[ERR] Query error for '{term}': {err_msg}")
            if "getaddrinfo" in err_msg or "11001" in err_msg or "ConnectTimeout" in err_msg:
                network_error = True
            all_passed = False

    if network_error:
        pytest.skip("Live Supabase database host unreachable from local test environment (DNS getaddrinfo)")

    assert all_passed, "Some search vocab terms were not resolved in DB table"


if __name__ == '__main__':
    test_vocab_lookup()
