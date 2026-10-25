"""
Test Search Vocabulary resolution for Phase 1 verification:
UITL201, ML, UHV, and GHRCE.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from methods.supabase_helper import init_supabase, init_supabase_admin

def test_vocab_lookup():
    client = init_supabase_admin() or init_supabase()
    if not client:
        print("[FAIL] Supabase client could not be initialized.")
        return False

    targets = ['uitl201', 'ml', 'uhv', 'ghrce']
    all_passed = True

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
            print(f"[ERR] Query error for '{term}': {e}")
            all_passed = False

    return all_passed

if __name__ == '__main__':
    test_vocab_lookup()
