import ast

path = r'e:\Users\abhihub\New folder\abhihub\app.py'
raw = open(path, 'rb').read()
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
    "        # Get user profile + college data\n        from methods.supabase_helper import get_student_profile, calculate_user_ranks\n        profile_res = get_student_profile(user_id)\n        profile_data = profile_res.get('data', {}) if profile_res.get('success') else {}\n        student_res = profile_res  # same call reuse result",
    'Merge get_user_profile + get_student_profile in /dashboard (1 call saved)'
)

# Fix the downstream usage — student_data was from student_res
app_rep(
    "        student_data = student_res.get('data', {}) if student_res.get('success') else {}",
    "        student_data = profile_data  # already fetched above",
    'Fix student_data reference after merge'
)

# 8. Import invalidate_files_cache at upload
app_rep(
    '        from methods.supabase_helper import save_file_record\n        \n        result = save_file_record(',
    '        from methods.supabase_helper import save_file_record, invalidate_files_cache\n        \n        result = save_file_record(',
    'Import invalidate_files_cache at upload'
)

if app != app_orig:
    output = app.replace('\n', '\r\n')
    open(path, 'wb').write(output.encode('utf-8'))
    print(f'Wrote app.py ({app_changes} changes)')
    try:
        ast.parse(app)
        print('Syntax OK')
    except SyntaxError as e:
        print(f'SyntaxError: {e}')
else:
    print('No changes to app.py')
