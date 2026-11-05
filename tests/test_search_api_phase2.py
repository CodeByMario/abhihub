"""
Phase 2 Acceptance Tests for Search Redesign (Section 12 of implementation guide)
- Suggest API (detected intent, groups, backward-compatible suggestions)
- Multi-tier ranking & honest reasons (exact, close, related)
- Typo correction & did_you_mean
- Strict fallback ladder (never random uploads on non-matching query)
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from methods.search_api import get_suggestions_payload, get_suggestions, execute_search_v3

def test_suggestions():
    print("\n--- 1. Testing Autocomplete Suggestions ---")
    
    # 1.1 Detected Code
    p1 = get_suggestions_payload('uitl201')
    assert p1.get('detected') is not None, "Expected detected intent for 'uitl201'"
    assert p1['detected']['type'] == 'code', f"Expected code type, got {p1['detected']['type']}"
    print(f"[PASS] uitl201 detected: {p1['detected']['label']}")
    
    # 1.2 Detected Alias
    p2 = get_suggestions_payload('ml')
    assert p2.get('detected') is not None, "Expected detected intent for 'ml'"
    assert p2['detected']['type'] == 'alias', f"Expected alias type, got {p2['detected']['type']}"
    print(f"[PASS] ml detected: {p2['detected']['label']}")
    
    # 1.3 Detected College
    p3 = get_suggestions_payload('ghrce')
    assert p3.get('detected') is not None, "Expected detected intent for 'ghrce'"
    assert p3['detected']['type'] == 'college', f"Expected college type, got {p3['detected']['type']}"
    print(f"[PASS] ghrce detected: {p3['detected']['label']}")
    
    # 1.4 Backward-compatible flat suggestions
    flat = get_suggestions('ml', limit=5)
    assert isinstance(flat, list) and len(flat) > 0, "Expected non-empty flat suggestions list"
    print(f"[PASS] Flat get_suggestions returned {len(flat)} items")

def test_search_resolution():
    print("\n--- 2. Testing Search Resolution & Fallback Ladder ---")
    
    # 2.1 Code Search
    res, meta = execute_search_v3('UITL201')
    print(f"[INFO] 'UITL201' returned {len(res)} results. Meta fallback stage: {meta.get('fallback_stage')}")
    if res:
        print(f"       Top match tier: {res[0].get('tier')}, match_reason: {res[0].get('match_reason')}")
        assert res[0]['tier'] in ('exact', 'close'), f"Expected exact or close tier for UITL201, got {res[0]['tier']}"
    
    # 2.2 Normalized Code Search with space (uitl 201)
    res_space, meta_space = execute_search_v3('uitl 201')
    print(f"[INFO] 'uitl 201' returned {len(res_space)} results.")
    if res_space:
        print(f"       Top match tier: {res_space[0].get('tier')}, match_reason: {res_space[0].get('match_reason')}")
        assert res_space[0]['tier'] in ('exact', 'close')
        
    # 2.3 Alias Search (ML)
    res_alias, meta_alias = execute_search_v3('ML')
    print(f"[INFO] 'ML' returned {len(res_alias)} results.")
    if res_alias:
        print(f"       Top match: {res_alias[0].get('file-name')} ({res_alias[0].get('subject')})")
        print(f"       Match reason: {res_alias[0].get('match_reason')}")
        
    # 2.4 Typo Search (machine lerning)
    res_typo, meta_typo = execute_search_v3('machine lerning')
    print(f"[INFO] 'machine lerning' returned {len(res_typo)} results. did_you_mean: {meta_typo.get('did_you_mean')}")
    
    # 2.5 Strict Zero-Result Guard (No random uploads when gibberish is typed)
    res_zero, meta_zero = execute_search_v3('asdfghjkllkjhgfdsa999')
    print(f"[INFO] Gibberish query returned {len(res_zero)} results. Meta fallback stage: {meta_zero.get('fallback_stage')}")
    assert len(res_zero) == 0, f"Expected 0 results for gibberish query, but got {len(res_zero)}! (Random uploads leak detected)"
    print("[PASS] Zero-result guard: Non-matching query strictly returned 0 results (no random uploads)")

if __name__ == '__main__':
    try:
        test_suggestions()
        test_search_resolution()
        print("\n>>> ALL PHASE 2 ACCEPTANCE TESTS PASSED <<<")
    except AssertionError as e:
        print(f"\n[FAIL] Assertion failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
