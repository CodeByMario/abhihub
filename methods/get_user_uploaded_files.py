def get_user_uploaded_files(user_email: str, limit: int = 20) -> Dict:
    """
    Get files uploaded by a specific user from file_records table.
    
    Args:
        user_email: Email of the user
        limit: Maximum number of files to return (default 20)
    
    Returns:
        dict: {'success': bool, 'message': str, 'data': list}
    """
    client = init_supabase()
    
    if not client:
        return {
            'success': False,
            'message': 'Supabase client not initialized',
            'data': []
        }
    
    try:
        print(f"[get_user_uploaded_files] Fetching files for user: {user_email}")
        
        # Query documents table for user's uploaded files in abhihub schema
        # Resolve user_id from email first to be safe, or join profiles
        p_res = client.table('profiles').select('id').eq('email', user_email).execute()
        if not p_res.data:
             return {'success': True, 'data': [], 'count': 0}
        
        u_id = p_res.data[0]['id']

        response = client.table('documents') \
            .select('id, title, file_url, document_category, created_at, uploader_id') \
            .eq('uploader_id', u_id) \
            .order('created_at', desc=True) \
            .limit(limit) \
            .execute()
        
        if response.data:
            print(f"[get_user_uploaded_files] Found {len(response.data)} files")
            return {
                'success': True,
                'data': response.data,
                'count': len(response.data)
            }
        else:
            print(f"[get_user_uploaded_files] No files found for user")
            return {
                'success': True,
                'data': [],
                'count': 0
            }
    
    except Exception as e:
        print(f"[get_user_uploaded_files] ERROR: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'message': f'Error fetching user files: {str(e)}',
            'data': []
        }
