# Store Room API Endpoint - to be added to app.py after line 450

@app.route('/store-room/api/label', methods=['POST'])
@auth_required
def label_store_room_paper():
    """
    Label a paper from store room and save to file_records table.
    Expects JSON with: filename, url, college_name, subject_name, branch, year, exam_type, etc.
    """
    try:
        # Get user info from session
        user_info = session.get('user', {})
        user_id = user_info.get('uid', '')
        user_email = user_info.get('email', '')
        
        if not user_email:
            return jsonify({
                'success': False,
                'message': 'User not authenticated'
            }), 401
        
        # Get JSON data from request
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400
        
        # Extract required fields
        filename = data.get('filename', '')
        file_url = data.get('url', '')
        college_name = data.get('college_name', '')
        subject_name = data.get('subject_name', '')
        branch_name = data.get('branch', '')
        year = str(data.get('year', ''))
        exam_type = data.get('exam_type', 'PYQ')  # Default to PYQ
        
        # Validate required fields
        if not all([filename, file_url, college_name, subject_name, branch_name, year]):
            return jsonify({
                'success': False,
                'message': 'Missing required fields'
            }), 400
        
        print(f"[STORE_ROOM_LABEL] User: {user_email}, File: {filename}")
        print(f"[STORE_ROOM_LABEL] College: {college_name}, Branch: {branch_name}")
        print(f"[STORE_ROOM_LABEL] Subject: {subject_name}, Year: {year}, Type: {exam_type}")
        
        # Look up college_id from college name
        from methods.supabase_helper import init_supabase
        client = init_supabase()
        
        college_id = None
        branch_id = None
        
        if client:
            # Lookup college
            try:
                # Table name is 'colleges' in abhihub schema
                college_response = client.table('colleges').select('id').ilike('name', college_name).limit(1).execute()
                if college_response.data and len(college_response.data) > 0:
                    college_id = college_response.data[0]['id']
                    print(f"[STORE_ROOM_LABEL] Found college_id: {college_id}")
                else:
                    print(f"[STORE_ROOM_LABEL] WARNING: College '{college_name}' not found in database")
            except Exception as e:
                print(f"[STORE_ROOM_LABEL] Error looking up college: {e}")
            
            # Lookup branch (department in abhihub schema)
            try:
                # Table name is 'departments' in abhihub schema
                branch_response = client.table('departments').select('id').ilike('name', branch_name).limit(1).execute()
                if branch_response.data and len(branch_response.data) > 0:
                    branch_id = branch_response.data[0]['id']
                    print(f"[STORE_ROOM_LABEL] Found branch_id: {branch_id}")
                else:
                    print(f"[STORE_ROOM_LABEL] WARNING: Branch '{branch_name}' not found in database")
            except Exception as e:
                print(f"[STORE_ROOM_LABEL] Error looking up branch: {e}")
        
        # Extract cloudinary_public_id from URL
        # URL format: https://res.cloudinary.com/[cloud]/[type]/upload/[transformations]/[public_id].[ext]
        cloudinary_public_id = filename  # Default fallback
        if 'cloudinary.com' in file_url:
            parts = file_url.split('/')
            if len(parts) > 7:
                # Extract public_id (everything after 'upload/')
                upload_idx = -1
                for i, part in enumerate(parts):
                    if part == 'upload':
                        upload_idx = i
                        break
                if upload_idx > 0 and upload_idx + 1 < len(parts):
                    # Join all parts after 'upload/', remove extension
                    public_id_with_ext = '/'.join(parts[upload_idx + 1:])
                    # Remove file extension
                    cloudinary_public_id = public_id_with_ext.rsplit('.', 1)[0]
                    print(f"[STORE_ROOM_LABEL] Extracted cloudinary_public_id: {cloudinary_public_id}")
        
        # Determine file type and size
        # For store room files, we can estimate or use defaults
        file_ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'jpg'
        file_type = 'pdf' if file_ext == 'pdf' else 'image'
        file_size = 0  # We don't have size info from Cloudinary URL, use 0 as placeholder
        
        # Save to file_records table
        from methods.supabase_helper import save_file_record
        
        result = save_file_record(
            user_id=user_id or user_email.split('@')[0],
            user_email=user_email,
            file_name=filename,
            file_url=file_url,
            file_type=file_type,
            file_size=file_size,
            cloudinary_public_id=cloudinary_public_id,
            subject_name=subject_name,
            document_type=exam_type,  # Map exam_type to document_type
            year=year,
            college_id=college_id,
            branch_id=branch_id
        )
        
        if result.get('success'):
            print(f"[STORE_ROOM_LABEL] SUCCESS: Saved to file_records")
            return jsonify({
                'success': True,
                'message': 'Paper labeled successfully',
                'data': result.get('data', {})
            }), 200
        else:
            print(f"[STORE_ROOM_LABEL] ERROR: {result.get('message')}")
            return jsonify({
                'success': False,
                'message': result.get('message', 'Failed to save label')
            }), 500
    
    except Exception as e:
        print(f"[STORE_ROOM_LABEL] EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Error labeling paper: {str(e)}'
        }), 500
