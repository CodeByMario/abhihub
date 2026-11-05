"""
Optimization patcher script for AbhiHub.
Applies Phase 1, Phase 2, Phase 3, Phase 5, Phase 6 optimizations cleanly.
"""
import os
import re

def patch_scoring_engine():
    path = os.path.join('methods', 'scoring_engine.py')
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    target = """        profile = client.table("profiles").select(
            "paper_quota_remaining"
        ).eq("id", user_id).limit(1).execute()
        if not profile.data:
            logging.warning("[ScoringEngine] no quota profile found for user %s", user_id)
            remaining_credits = 0
        else:
            remaining_credits = max(
                0, int(profile.data[0].get("paper_quota_remaining") or 0)
            )

        if remaining_credits == 0:
            density = "high"
        elif remaining_credits < 5:
            density = "medium"
        elif remaining_credits < 10:
            density = "low"
        elif remaining_credits < 20:
            density = "minimum"
        else:
            density = "monthly"

        verified_upload_count = 0
        try:
            uploads = client.table("documents").select(
                "id", count="exact"
            ).eq("uploader_id", user_id).eq("status", "approved").limit(1).execute()
            verified_upload_count = int(
                getattr(uploads, "count", None)
                if getattr(uploads, "count", None) is not None
                else len(uploads.data or [])
            )
        except Exception as upload_error:
            logging.warning(
                "[ScoringEngine] verified upload lookup failed for %s: %s",
                user_id,
                upload_error,
            )"""

    replacement = """        # Check L1 cache to avoid redundant Supabase queries on every navigation
        user_metrics = None
        cache = None
        try:
            from cache_manager import get_cache
            cache = get_cache()
            user_metrics, _ = cache.l1.get(f"user_ad_metrics:{user_id}")
        except Exception:
            cache = None

        if user_metrics is not None:
            remaining_credits, verified_upload_count = user_metrics
        else:
            profile = client.table("profiles").select(
                "paper_quota_remaining"
            ).eq("id", user_id).limit(1).execute()
            if not profile.data:
                logging.warning("[ScoringEngine] no quota profile found for user %s", user_id)
                remaining_credits = 0
            else:
                remaining_credits = max(
                    0, int(profile.data[0].get("paper_quota_remaining") or 0)
                )

            verified_upload_count = 0
            try:
                uploads = client.table("documents").select(
                    "id", count="exact"
                ).eq("uploader_id", user_id).eq("status", "approved").limit(1).execute()
                verified_upload_count = int(
                    getattr(uploads, "count", None)
                    if getattr(uploads, "count", None) is not None
                    else len(uploads.data or [])
                )
            except Exception as upload_error:
                logging.warning(
                    "[ScoringEngine] verified upload lookup failed for %s: %s",
                    user_id,
                    upload_error,
                )
            if cache:
                cache.l1.set(f"user_ad_metrics:{user_id}", (remaining_credits, verified_upload_count), ttl=90)

        if remaining_credits == 0:
            density = "high"
        elif remaining_credits < 5:
            density = "medium"
        elif remaining_credits < 10:
            density = "low"
        elif remaining_credits < 20:
            density = "minimum"
        else:
            density = "monthly\""""

    if target in content:
        content = content.replace(target, replacement, 1)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print("Patched methods/scoring_engine.py")
    else:
        print("Target not found in methods/scoring_engine.py")

def patch_guide_service():
    path = os.path.join('methods', 'guide_service.py')
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Update get_user_guide_progress to cache in L1 and select specific fields
    target = """def get_user_guide_progress(user_id):
    \"\"\"Fetch all guide progress records for a user with session fallback.\"\"\"
    from flask import session
    session_progress = session.get('guide_progress', {})

    client = init_supabase_admin() or init_supabase()
    if not client or not user_id:
        return session_progress
    try:
        tbl = _get_table(client)
        res = tbl.select('*').eq('user_id', str(user_id)).execute()
        if res.data:
            merged = dict(session_progress)
            merged.update({row['guide_id']: row for row in res.data})
            return merged
    except Exception as e:
        logging.warning(f"[GUIDE] Progress fetch error: {e}")
    return session_progress"""

    replacement = """def get_user_guide_progress(user_id):
    \"\"\"Fetch all guide progress records for a user with L1 cache and session fallback.\"\"\"
    from flask import session
    session_progress = session.get('guide_progress', {})
    if not user_id:
        return session_progress

    # Check L1 cache
    cache = None
    try:
        from cache_manager import get_cache
        cache = get_cache()
        cached, _ = cache.l1.get(f"user_guide_progress:{user_id}")
        if cached is not None:
            return cached
    except Exception:
        cache = None

    client = init_supabase_admin() or init_supabase()
    if not client:
        return session_progress
    try:
        tbl = _get_table(client)
        # Select explicit fields required by guide evaluator (avoids SELECT *)
        res = tbl.select('guide_id, status, current_step, version, updated_at').eq('user_id', str(user_id)).execute()
        if res.data:
            merged = dict(session_progress)
            merged.update({row['guide_id']: row for row in res.data})
            if cache:
                cache.l1.set(f"user_guide_progress:{user_id}", merged, ttl=180)
            return merged
    except Exception as e:
        logging.warning(f"[GUIDE] Progress fetch error: {e}")
    if cache:
        cache.l1.set(f"user_guide_progress:{user_id}", session_progress, ttl=60)
    return session_progress"""

    if target in content:
        content = content.replace(target, replacement, 1)

    # 2. Invalidate cache on update_guide_progress
    target_update = """    except Exception as e:
        logging.warning(f"[GUIDE] Progress write error: {e}")
        return False
    return True"""

    replacement_update = """        try:
            from cache_manager import get_cache
            get_cache().l1.delete(f"user_guide_progress:{user_id}")
        except Exception:
            pass
    except Exception as e:
        logging.warning(f"[GUIDE] Progress write error: {e}")
        return False
    return True"""

    if target_update in content:
        content = content.replace(target_update, replacement_update, 1)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patched methods/guide_service.py")

def patch_supabase_helper():
    path = os.path.join('methods', 'supabase_helper.py')
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Optimize get_all_files_merged projection (drop heavy joins for comments/votes in catalogue)
    target_proj = """        projections = (
            '*, profiles!documents_uploader_id_fkey(full_name, email), '
            'subjects(name, subject_code), colleges(name, abbreviation), '
            'document_votes(user_id), bookmarks(user_id), document_comments(id)',
            '*, profiles!documents_uploader_id_fkey(full_name, email), '
            'subjects(name, subject_code), colleges(name, abbreviation)',
            '*',
        )"""

    replacement_proj = """        projections = (
            'id, title, storage_provider, file_url, thumbnail_url, view_count, status, '
            'college_id, subject_id, branch_id, semester, exam_type, year, created_at, '
            'updated_at, is_bookmarked, uploader_id, price, '
            'profiles!documents_uploader_id_fkey(full_name, email), '
            'subjects(name, subject_code), colleges(name, abbreviation)',
            'id, title, storage_provider, file_url, thumbnail_url, view_count, status, '
            'college_id, subject_id, branch_id, semester, exam_type, year, created_at, '
            'updated_at, is_bookmarked, uploader_id, price, '
            'subjects(name, subject_code), colleges(name, abbreviation)',
            'id, title, storage_provider, file_url, thumbnail_url, view_count, status, '
            'college_id, subject_id, branch_id, semester, exam_type, year, created_at, '
            'updated_at, is_bookmarked, uploader_id, price',
        )"""

    if target_proj in content:
        content = content.replace(target_proj, replacement_proj, 1)
        print("Optimized catalogue projections in get_all_files_merged")

    # 2. Optimize get_user_file_history with L1 cache and fast-path user_id
    target_history = """def get_user_file_history(user_email: str = '', user_id: str = None, limit: int = 10) -> Dict:
    \"\"\"
    Get file access history for a user using document_views table.
    \"\"\"
    client = init_supabase()
    if not client: 
        return {'success': False, 'data': []}
    
    try:
        # Resolve user_id if not directly passed
        if not user_id and user_email:
            profile_res = client.table('profiles').select('id').eq('email', user_email).limit(1).execute()
            if profile_res.data:
                user_id = profile_res.data[0]['id']
        
        if not user_id:
            return {'success': False, 'data': [], 'message': 'User not found'}
        
        # Query document_views with document details
        res = client.table('document_views') \\
            .select('id, document_id, accessed_at, documents(id, title, file_url, file_type, document_category)') \\
            .eq('user_id', user_id) \\
            .order('accessed_at', desc=True) \\
            .limit(limit) \\
            .execute()"""

    replacement_history = """def get_user_file_history(user_email: str = '', user_id: str = None, limit: int = 10) -> Dict:
    \"\"\"
    Get file access history for a user using document_views table with L1 caching.
    \"\"\"
    cache = None
    c_key = None
    try:
        from cache_manager import get_cache
        cache = get_cache()
        if user_id:
            c_key = f"user_file_history:{user_id}:{limit}"
            cached_data, _ = cache.l1.get(c_key)
            if cached_data is not None:
                return {'success': True, 'data': cached_data, 'count': len(cached_data)}
    except Exception:
        cache = None

    client = init_supabase()
    if not client: 
        return {'success': False, 'data': []}
    
    try:
        # Resolve user_id if not directly passed
        if not user_id and user_email:
            profile_res = client.table('profiles').select('id').eq('email', user_email).limit(1).execute()
            if profile_res.data:
                user_id = profile_res.data[0]['id']
        
        if not user_id:
            return {'success': False, 'data': [], 'message': 'User not found'}
        
        if not c_key and cache:
            c_key = f"user_file_history:{user_id}:{limit}"
            cached_data, _ = cache.l1.get(c_key)
            if cached_data is not None:
                return {'success': True, 'data': cached_data, 'count': len(cached_data)}

        # Query document_views with document details (project specific columns)
        res = client.table('document_views') \\
            .select('id, document_id, accessed_at, documents(id, title, file_url, file_type, document_category)') \\
            .eq('user_id', user_id) \\
            .order('accessed_at', desc=True) \\
            .limit(limit) \\
            .execute()"""

    if target_history in content:
        content = content.replace(target_history, replacement_history, 1)

    # In get_user_file_history return: store in cache
    target_hist_ret = """        return {
            'success': True,
            'data': formatted_history,
            'count': len(formatted_history)
        }"""
    replacement_hist_ret = """        if cache and c_key:
            cache.l1.set(c_key, formatted_history, ttl=60)
        return {
            'success': True,
            'data': formatted_history,
            'count': len(formatted_history)
        }"""
    if target_hist_ret in content:
        content = content.replace(target_hist_ret, replacement_hist_ret, 1)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patched methods/supabase_helper.py")

def patch_api_routes():
    path = os.path.join('routes', 'api.py')
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Pass user_id directly to get_user_file_history
    target_history_call = """        from methods.supabase_helper import get_user_file_history
        result = get_user_file_history(user_email=user_email, limit=limit)"""
    replacement_history_call = """        from methods.supabase_helper import get_user_file_history
        user_id = user_info.get('uid') or user_info.get('id')
        result = get_user_file_history(user_email=user_email, user_id=user_id, limit=limit)"""

    if target_history_call in content:
        content = content.replace(target_history_call, replacement_history_call, 1)
        print("Optimized api_get_file_access_history in routes/api.py")

    # 2. Handle material_requests table 404 properly (do not return false success)
    target_mat_req = """        return jsonify({'success': True, 'requests': items}), 200
    except Exception as e:
        return jsonify({'success': True, 'requests': []}), 200"""

    replacement_mat_req = """        return jsonify({'success': True, 'requests': items}), 200
    except Exception as e:
        err_msg = str(e)
        if 'PGRST205' in err_msg or 'material_requests' in err_msg:
            logging.warning("[MaterialRequests] Table 'material_requests' not found in schema cache. Migration pending: migrations/017_material_requests_table.sql")
            return jsonify({
                'success': False,
                'error': 'table_not_found',
                'message': 'Database table material_requests has not been migrated yet. Please apply migrations/017_material_requests_table.sql',
                'requests': []
            }), 404
        logging.error(f"[MaterialRequests] Unexpected error: {e}")
        return jsonify({'success': False, 'message': 'Database error', 'requests': []}), 500"""

    if target_mat_req in content:
        content = content.replace(target_mat_req, replacement_mat_req, 1)
        print("Fixed material-requests 404 handling in routes/api.py")

    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == '__main__':
    patch_scoring_engine()
    patch_guide_service()
    patch_supabase_helper()
    patch_api_routes()
    print("Done applying optimization patches.")
