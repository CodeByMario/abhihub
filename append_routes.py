# Append routes to app.py
def append_routes():
    file_path = "e:/code/projects/abhiHub/abhihub/abhi-hub/app.py"
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    routes = """

# ─── Social Interactions: Like, Bookmark, Comment ─────────────────────────
@app.route('/api/like', methods=['POST'])
@auth_required
def toggle_like_route():
    try:
        user = session.get('user', {})
        user_id = user.get('uid')
        data = request.get_json(silent=True) or {}
        document_id = data.get('document_id')
        
        if not document_id:
            return jsonify({'success': False, 'message': 'document_id is required'}), 400
            
        from methods.supabase_helper import toggle_like
        res = toggle_like(user_id, document_id)
        return jsonify(res), 200 if res.get('success') else 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/bookmark', methods=['POST'])
@auth_required
def toggle_bookmark_route():
    try:
        user = session.get('user', {})
        user_id = user.get('uid')
        data = request.get_json(silent=True) or {}
        document_id = data.get('document_id')
        
        if not document_id:
            return jsonify({'success': False, 'message': 'document_id is required'}), 400
            
        from methods.supabase_helper import toggle_bookmark
        res = toggle_bookmark(user_id, document_id)
        return jsonify(res), 200 if res.get('success') else 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/comment', methods=['POST'])
@auth_required
def add_comment_route():
    try:
        user = session.get('user', {})
        user_id = user.get('uid')
        data = request.get_json(silent=True) or {}
        document_id = data.get('document_id')
        content = data.get('content')
        
        if not document_id or not content:
            return jsonify({'success': False, 'message': 'document_id and content are required'}), 400
            
        from methods.supabase_helper import add_comment
        res = add_comment(user_id, document_id, content)
        return jsonify(res), 200 if res.get('success') else 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/comments/<document_id>', methods=['GET'])
def get_comments_route(document_id):
    try:
        if not document_id:
            return jsonify({'success': False, 'message': 'document_id is required'}), 400
            
        from methods.supabase_helper import get_comments
        res = get_comments(document_id)
        return jsonify(res), 200 if res.get('success') else 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
# ────────────────────────────────────────────────────────────────────────────
"""
    if "@app.route('/api/like'" not in content:
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(routes)

if __name__ == "__main__":
    append_routes()
