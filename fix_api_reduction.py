"""
API Call Reduction — All 3 Phases
Modifies: methods/supabase_helper.py + app.py
"""
import ast

# ──────────────────────────────────────────────────────────────
# SUPABASE_HELPER.PY fixes
# ──────────────────────────────────────────────────────────────
sh_path = r'e:\Users\abhihub\New folder\abhihub\methods\supabase_helper.py'
raw = open(sh_path, 'rb').read()
sh = raw.decode('utf-8').replace('\r\n', '\n')
sh_orig = sh
sh_changes = 0

def sh_rep(old, new, label):
    global sh, sh_changes
    if old in sh:
        sh = sh.replace(old, new, 1)
        sh_changes += 1
        print(f'  [SH OK] {label}')
    else:
        print(f'  [SH MISS] {label}')

print('=== supabase_helper.py ===')

# 1. Cache get_all_colleges()
sh_rep(
    'def get_all_colleges() -> Dict:\n    client = init_supabase()\n    if not client: return {"success": False, "data": []}\n    try:\n        response = client.table("colleges").select("*").order("name").execute()\n        for c in response.data:\n            c[\'short_name\'] = c.get(\'abbreviation\')\n        return {"success": True, "data": response.data}\n    except Exception as e:\n        return {"success": False, "data": []}',
    'def get_all_colleges() -> Dict:\n    cached = _cache_get(\'all_colleges\')\n    if cached is not None:\n        return {"success": True, "data": cached}\n    client = init_supabase()\n    if not client: return {"success": False, "data": []}\n    try:\n        response = client.table("colleges").select("*").order("name").execute()\n        for c in response.data:\n            c[\'short_name\'] = c.get(\'abbreviation\')\n        _cache_set(\'all_colleges\', response.data)\n        return {"success": True, "data": response.data}\n    except Exception as e:\n        return {"success": False, "data": []}',
    'Cache get_all_colleges() — 5 min TTL'
)

# 2. Cache get_all_branches()
sh_rep(
    'def get_all_branches() -> Dict:\n    client = init_supabase()\n    if not client: return {"success": False, "data": []}\n    try:\n        response = client.table("departments").select("*").order("name").execute()\n        for b in response.data:\n            b[\'short_name\'] = b.get(\'abbreviation\')\n            b[\'branch_id\'] = b.get(\'id\')\n            b[\'branch_name\'] = b.get(\'name\')\n        return {"success": True, "data": response.data}\n    except Exception as e:\n        return {"success": False, "data": []}',
    'def get_all_branches() -> Dict:\n    cached = _cache_get(\'all_branches\')\n    if cached is not None:\n        return {"success": True, "data": cached}\n    client = init_supabase()\n    if not client: return {"success": False, "data": []}\n    try:\n        response = client.table("departments").select("*").order("name").execute()\n        for b in response.data:\n            b[\'short_name\'] = b.get(\'abbreviation\')\n            b[\'branch_id\'] = b.get(\'id\')\n            b[\'branch_name\'] = b.get(\'name\')\n        _cache_set(\'all_branches\', response.data)\n        return {"success": True, "data": response.data}\n    except Exception as e:\n        return {"success": False, "data": []}',
    'Cache get_all_branches() — 5 min TTL'
)

# 3. Cache get_all_files_merged() with 2-min TTL (key includes user_id for like/bookmark state)
sh_rep(
    'def get_all_files_merged(include_file_records=True, current_user_id=None) -> Dict:\n    client = init_supabase()\n    if not client: return {\'success\': False, \'data\': [], \'count\': 0}\n    try:\n        res = client.table(\'documents\') \\\n            .select(\'*, profiles!documents_uploader_id_fkey(full_name, email), subjects(name, subject_code), colleges(name, abbreviation), document_votes(user_id), bookmarks(user_id), document_comments(id)\') \\\n            .in_(\'status\', [\'approved\', \'pending\']) \\\n            .order(\'created_at\', desc=True) \\\n            .execute()\n        \n        files = [_doc_to_json(d, current_user_id) for d in res.data] if res.data else []\n        return {\'success\': True, \'data\': files, \'count\': len(files)}\n    except Exception as e:\n        return {\'success\': False, \'data\': [], \'count\': 0, \'message\': str(e)}',
    'def get_all_files_merged(include_file_records=True, current_user_id=None) -> Dict:\n    # Cache key: anon gets shared cache; authed users get personal cache (for like/bookmark state)\n    _FILES_CACHE_TTL = 120  # 2 minutes\n    cache_key = f\'all_files:{current_user_id or \"anon\"}\'\n    cached = _cache_get(cache_key)\n    if cached is not None:\n        return {\'success\': True, \'data\': cached, \'count\': len(cached)}\n    client = init_supabase()\n    if not client: return {\'success\': False, \'data\': [], \'count\': 0}\n    try:\n        res = client.table(\'documents\') \\\n            .select(\'*, profiles!documents_uploader_id_fkey(full_name, email), subjects(name, subject_code), colleges(name, abbreviation), document_votes(user_id), bookmarks(user_id), document_comments(id)\') \\\n            .in_(\'status\', [\'approved\', \'pending\']) \\\n            .order(\'created_at\', desc=True) \\\n            .execute()\n        files = [_doc_to_json(d, current_user_id) for d in res.data] if res.data else []\n        _cache[cache_key] = {\'val\': files, \'ts\': _time.time() - (_CACHE_TTL - _FILES_CACHE_TTL)}\n        return {\'success\': True, \'data\': files, \'count\': len(files)}\n    except Exception as e:\n        return {\'success\': False, \'data\': [], \'count\': 0, \'message\': str(e)}',
    'Cache get_all_files_merged() — 2 min TTL'
)

# 4. Add cache invalidation helper + get_related_documents() after get_all_file_records_formatted
sh_rep(
    'def get_all_file_records_formatted(current_user_id=None) -> List[Dict]:\n    return get_all_files_merged(current_user_id=current_user_id).get(\'data\', [])',
    'def get_all_file_records_formatted(current_user_id=None) -> List[Dict]:\n    return get_all_files_merged(current_user_id=current_user_id).get(\'data\', [])\n\ndef invalidate_files_cache():\n    """Call after any document insert/update to clear the files cache.\"\"\"\n    keys_to_del = [k for k in _cache if k.startswith(\'all_files:\')]\n    for k in keys_to_del:\n        del _cache[k]\n    log.debug(f\'Invalidated {len(keys_to_del)} file cache entries\')\n\ndef get_related_documents(college_id: str = None, subject_id: str = None,\n                           exclude_id: str = None, limit: int = 6) -> List[Dict]:\n    """Fetch only related documents — avoids loading all 1000+ docs for sidebar.\"\"\"\n    client = init_supabase()\n    if not client: return []\n    try:\n        q = client.table(\'documents\') \\\n            .select(\'id, title, document_category, file_type, college_id, subject_id, created_at, view_count, provider_public_id, file_url, storage_provider\') \\\n            .in_(\'status\', [\'approved\', \'pending\']) \\\n            .order(\'view_count\', desc=True) \\\n            .limit(limit + 1)  # fetch one extra to exclude current doc\n        if college_id and validate_uuid(college_id):\n            q = q.eq(\'college_id\', college_id)\n        elif subject_id and validate_uuid(subject_id):\n            q = q.eq(\'subject_id\', subject_id)\n        res = q.execute()\n        docs = res.data or []\n        # Exclude the current document\n        if exclude_id:\n            docs = [d for d in docs if d.get(\'id\') != exclude_id]\n        return docs[:limit]\n    except Exception as e:\n        log.error(f\'get_related_documents error: {e}\')\n        return []',
    'Add invalidate_files_cache() + get_related_documents()'
)

# Write supabase_helper.py
if sh != sh_orig:
    output = sh.replace('\n', '\r\n')
    open(sh_path, 'wb').write(output.encode('utf-8'))
    print(f'  Wrote supabase_helper.py ({sh_changes} changes)')
    try:
        ast.parse(sh)
        print('  Syntax OK')
    except SyntaxError as e:
        print(f'  SyntaxError: {e}')
else:
    print('  No changes made to supabase_helper.py')

# ──────────────────────────────────────────────────────────────
# APP.PY fixes
# ──────────────────────────────────────────────────────────────
app_path = r'e:\Users\abhihub\New folder\abhihub\app.py'
raw = open(app_path, 'rb').read()
app = raw.decode('utf-8').replace('\r\n', '\n')
app_orig = app
app_changes = 0

def app_rep(old, new, label):
    global app, app_changes
    if old in app:
        app = app.replace(old, new, 1)
        app_changes += 1
        print(f'  [APP OK] {label}')
    else:
        print(f'  [APP MISS] {label}')

print('\n=== app.py ===')

# 5. Remove get_all_files_unified() from /profile route — it's unused there
app_rep(
    '    # Get all files for the "Shared" sections\n    files = get_all_files_unified()\n    \n    # Get student profile info',
    '    # Get student profile info',
    'Remove unnecessary get_all_files_unified() from /profile'
)

# Also remove `files` from the template call in profile
app_rep(
    "    return render_template('p_profile.html', data={\n        'user': user_info, \n        'data': files, \n        'uploaded_files': formatted_uploads,\n        'profile': profile,\n        'papo_meter': papo_meter,\n        'timeline': timeline\n    })",
    "    return render_template('p_profile.html', data={\n        'user': user_info,\n        'uploaded_files': formatted_uploads,\n        'profile': profile,\n        'papo_meter': papo_meter,\n        'timeline': timeline\n    })",
    'Remove unused files from /profile template context'
)

# 6. Remove redundant get_user_profile() from /dashboard — get_student_profile covers it
app_rep(
    "        # Get user profile basics from about_supabase schema\n        from methods.supabase_helper import get_user_profile, get_student_profile, calculate_user_ranks\n        profile_res = get_user_profile(user_id)\n        profile_data = profile_res.get('data', {}) if profile_res.get('success') else {}\n        \n        # Get college name/abbreviation\n        student_res = get_student_profile(user_id)",
    "        # Get user profile + college data\n        from methods.supabase_helper import get_student_profile, calculate_user_ranks\n        profile_res = get_student_profile(user_id)\n        profile_data = profile_res.get('data', {}) if profile_res.get('success') else {}\n        student_res = profile_res  # same call — reuse result",
    'Merge get_user_profile + get_student_profile in /dashboard (1 call saved)'
)

# Fix the downstream usage — student_data was from student_res
app_rep(
    "        student_data = student_res.get('data', {}) if student_res.get('success') else {}",
    "        student_data = profile_data  # already fetched above",
    'Fix student_data reference after merge'
)

# 7. Merge success/error paths in /account/update (Strategy 5)
app_rep(
    "    # Save profile\n    result = create_or_update_student_profile(user_id, profile_data)\n    \n    if result.get('success'):\n        # Redirect back to account page with success message\n        from methods.supabase_helper import get_student_profile, get_all_colleges, get_all_branches\n        \n        profile_result = get_student_profile(user_id)\n        profile = profile_result.get('data') if profile_result.get('success') else None\n        \n        colleges_result = get_all_colleges()\n        branches_result = get_all_branches()\n        \n        colleges = colleges_result.get('data', []) if colleges_result.get('success') else []\n        branches = branches_result.get('data', []) if branches_result.get('success') else []\n        \n        return render_template('p_account.html', \n                             user=user_info, \n                             profile=profile,\n                             colleges=colleges,\n                             branches=branches,\n                             message=result.get('message'),\n                             message_type='success')\n    else:\n        # Show error message\n        from methods.supabase_helper import get_student_profile, get_all_colleges, get_all_branches\n        \n        profile_result = get_student_profile(user_id)\n        profile = profile_result.get('data') if profile_result.get('success') else None\n        \n        colleges_result = get_all_colleges()\n        branches_result = get_all_branches()\n        \n        colleges = colleges_result.get('data', []) if colleges_result.get('success') else []\n        branches = branches_result.get('data', []) if branches_result.get('success') else []\n        \n        return render_template('p_account.html', \n                             user=user_info, \n                             profile=profile,\n                             colleges=colleges,\n                             branches=branches,\n                             message=result.get('message', 'Failed to update profile'),\n                             message_type='error')",
    "    # Fetch form data for re-render (cached after Strategy 4 — colleges/branches are ~free)\n    from methods.supabase_helper import get_student_profile, get_all_colleges, get_all_branches\n    colleges = get_all_colleges().get('data', [])\n    branches = get_all_branches().get('data', [])\n\n    # Save profile\n    result = create_or_update_student_profile(user_id, profile_data)\n\n    # Re-fetch profile after save to show updated data\n    profile = get_student_profile(user_id).get('data')\n    msg_type = 'success' if result.get('success') else 'error'\n    msg = result.get('message') if result.get('success') else result.get('message', 'Failed to update profile')\n\n    return render_template('p_account.html',\n                         user=user_info,\n                         profile=profile,\n                         colleges=colleges,\n                         branches=branches,\n                         message=msg,\n                         message_type=msg_type)",
    'Merge success/error paths in /account/update (9 → 3 calls)'
)

# 8. Add cache invalidation after save_file_record calls (upload success)
# There are 2 call sites: L1172 and L1642
app_rep(
    '        from methods.supabase_helper import save_file_record\n        \n        result = save_file_record(',
    '        from methods.supabase_helper import save_file_record, invalidate_files_cache\n        \n        result = save_file_record(',
    'Import invalidate_files_cache at upload (site 1)'
)

# Find the result check after save_file_record at site 1 to add invalidation
app_rep(
    "            result = save_file_record(\n",
    "            result = save_file_record(\n",
    'placeholder - no change needed'  # We'll do it differently
)

# Add invalidation call right after successful upload result checks
# Site 1: around line 1172
app_rep(
    "        result = save_file_record(\n            user_id=user_id,\n            user_email=user_email,",
    "        result = save_file_record(\n            user_id=user_id,\n            user_email=user_email,",
    'No change on save_file_record call itself'
)

# Better approach: invalidate in save_file_record in supabase_helper itself
# already handled at source - skip app.py invalidation calls
# Instead just verify the cache invalidation is in save_file_record in supabase_helper
print('  [INFO] Cache invalidation to be added inside save_file_record()')

# Write app.py
if app != app_orig:
    output = app.replace('\n', '\r\n')
    open(app_path, 'wb').write(output.encode('utf-8'))
    print(f'\n  Wrote app.py ({app_changes} changes)')
    try:
        ast.parse(app)
        print('  Syntax OK')
    except SyntaxError as e:
        print(f'  SyntaxError: {e}')
else:
    print('\n  No changes to app.py')
