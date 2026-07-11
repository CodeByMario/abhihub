import ast

path = r'e:\Users\abhihub\New folder\abhihub\app.py'
raw = open(path, 'rb').read()
src = raw.decode('utf-8').replace('\r\n', '\n')

old_code = """    # Save profile
    result = create_or_update_student_profile(user_id, profile_data)
    
    if result.get('success'):
        # Redirect back to account page with success message
        from methods.supabase_helper import get_student_profile, get_all_colleges, get_all_branches
        
        profile_result = get_student_profile(user_id)
        profile = profile_result.get('data') if profile_result.get('success') else None
        
        colleges_result = get_all_colleges()
        branches_result = get_all_branches()
        
        colleges = colleges_result.get('data', []) if colleges_result.get('success') else []
        branches = branches_result.get('data', []) if branches_result.get('success') else []
        
        return render_template('p_account.html', 
                             user=user_info, 
                             profile=profile,
                             colleges=colleges,
                             branches=branches,
                             message=result.get('message'),
                             message_type='success')
    else:
        # Show error message
        from methods.supabase_helper import get_student_profile, get_all_colleges, get_all_branches
        
        profile_result = get_student_profile(user_id)
        profile = profile_result.get('data') if profile_result.get('success') else None
        
        colleges_result = get_all_colleges()
        branches_result = get_all_branches()
        
        colleges = colleges_result.get('data', []) if colleges_result.get('success') else []
        branches = branches_result.get('data', []) if branches_result.get('success') else []
        
        return render_template('p_account.html', 
                             user=user_info, 
                             profile=profile,
                             colleges=colleges,
                             branches=branches,
                             message=result.get('message', 'Failed to update profile'),
                             message_type='error')"""

new_code = """    # Fetch static form data ONCE (colleges/branches are now cached)
    from methods.supabase_helper import get_student_profile, get_all_colleges, get_all_branches
    colleges = get_all_colleges().get('data', [])
    branches = get_all_branches().get('data', [])

    # Save profile
    result = create_or_update_student_profile(user_id, profile_data)

    # Re-fetch profile after save to reflect updated data
    profile_result = get_student_profile(user_id)
    profile = profile_result.get('data') if profile_result.get('success') else None
    
    msg_type = 'success' if result.get('success') else 'error'
    msg = result.get('message') or ('Profile updated!' if result.get('success') else 'Failed to update profile')

    return render_template('p_account.html',
                         user=user_info,
                         profile=profile,
                         colleges=colleges,
                         branches=branches,
                         message=msg,
                         message_type=msg_type)"""

if old_code in src:
    new_src = src.replace(old_code, new_code)
    try:
        ast.parse(new_src)
        print('Syntax OK')
        output = new_src.replace('\n', '\r\n')
        open(path, 'wb').write(output.encode('utf-8'))
        print('Updated app.py successfully')
    except SyntaxError as e:
        print(f'SyntaxError: {e}')
else:
    print('Error: old_code not found in app.py')
