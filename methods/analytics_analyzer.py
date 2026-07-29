"""
Background Analytics Analyzer
Analyzes search_analytics for zero-result queries and common misspellings to suggest new aliases.
"""
from methods.supabase_helper import init_supabase

def analyze_search_metrics():
    client = init_supabase()
    if not client: return False
    
    try:
        # Find queries with 0 results but high frequency
        res = client.table('search_analytics').select('query, results_count').eq('results_count', 0).execute()
        
        failed_queries = {}
        for r in (res.data or []):
            q = r.get('query', '').lower().strip()
            if q:
                failed_queries[q] = failed_queries.get(q, 0) + 1
                
        # Find those failing 5+ times
        common_misses = [q for q, count in failed_queries.items() if count >= 5]
        
        if common_misses:
            print(f"[Analytics Worker] High-frequency missing queries detected for admin review: {common_misses}")
            # Here we would typically insert into an `alias_suggestions` table for admin approval
            
        return True
    except Exception as e:
        print(f"Analytics analyzer error: {e}")
        return False
