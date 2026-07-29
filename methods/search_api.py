"""
Search API V2 Module
Implements stateless, scalable search against the search_documents table.
"""
from flask import request, jsonify
from methods.supabase_helper import init_supabase

def execute_search(query: str, college_id: str = None, limit: int = 50):
    client = init_supabase()
    if not client: return []
    
    try:
        def get_base_query():
            bq = client.table('search_documents').select('file_id, normalized_title, subjects(name, subject_code), college_id').eq('status', 'ready')
            if college_id and college_id.upper() != 'ALL' and len(college_id) == 36:
                bq = bq.eq('college_id', college_id)
            return bq
            
        if query:
            results = []
            seen_ids = set()
            
            # Helper to add results and filter duplicates
            def add_results(data):
                for r in data:
                    if r['file_id'] not in seen_ids:
                        results.append(r)
                        seen_ids.add(r['file_id'])
            
            # 1. Exact/Substring Match (Most relevant at top)
            exact_res = get_base_query().ilike('normalized_title', f'%{query}%').limit(limit).execute()
            if exact_res.data:
                add_results(exact_res.data)
                
            # 2. Fuzzy Match (Similar subjects)
            fuzzy_query = query.replace(" ", "%")
            if fuzzy_query != query and len(results) < limit:
                fuzzy_res = get_base_query().ilike('normalized_title', f'%{fuzzy_query}%').limit(limit).execute()
                if fuzzy_res.data:
                    add_results(fuzzy_res.data)
                    
            # 3. Individual Words Match (Broader similarity)
            if len(results) < limit and ' ' in query:
                words = [w for w in query.split() if len(w) > 2] # ignore small words
                if words:
                    or_filter = ",".join([f"normalized_title.ilike.%{w}%" for w in words])
                    word_res = get_base_query().or_(or_filter).limit(limit).execute()
                    if word_res.data:
                        add_results(word_res.data)
            
            results = results[:limit]
            
            if not results: return []
            
            # Fetch full document details for mapping
            file_ids = [r['file_id'] for r in results]
            docs_res = client.table('documents').select('*, profiles!documents_uploader_id_fkey(full_name), subjects(name, subject_code), colleges(name)').in_('id', file_ids).execute()
            docs_data = {d['id']: d for d in (docs_res.data or [])}
            
            mapped_results = []
            for r in results:
                doc = docs_data.get(r['file_id'])
                if not doc: continue
                
                subj = doc.get('subjects') or {}
                col = doc.get('colleges') or {}
                
                mapped_results.append({
                    'record_id': doc.get('id'),
                    'file-name': doc.get('title'),
                    'file-path': doc.get('file_url'),
                    'type': doc.get('document_category') or 'Papers',
                    'file-type': doc.get('file_type') or 'pdf',
                    'subject': subj.get('name'),
                    'subject_code': subj.get('subject_code'),
                    'college': col.get('name'),
                    'author': (doc.get('profiles') or {}).get('full_name') or 'Anonymous',
                    'view_count': doc.get('view_count') or 0,
                    'like_count': doc.get('like_count') or 0,
                    'bookmark_count': doc.get('bookmark_count') or 0,
                    'comment_count': 0,
                    'year': str(doc.get('created_at', ''))[:4] if doc.get('created_at') else '',
                    'date': doc.get('created_at', '')
                })
            
            return mapped_results
            
        return get_base_query().limit(limit).execute().data or []
        
    except Exception as e:
        print(f"Search V2 error: {e}")
        return []

def search_v2_endpoint():
    q = request.args.get('q', '').strip()
    college_id = request.args.get('college_id')
    
    results = execute_search(q, college_id)
    return jsonify({
        'success': True,
        'count': len(results),
        'results': results
    })

def search_analytics_endpoint():
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        results_count = data.get('results_count', 0)
        
        if query:
            client = init_supabase()
            if client:
                client.table('search_analytics').insert({
                    'query': query,
                    'results_count': results_count
                }).execute()
        return jsonify({'success': True})
    except Exception as e:
        print(f"Analytics error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
