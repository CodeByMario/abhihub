# We append functions to `methods/supabase_helper.py`
import json

def append_supabase_helpers():
    file_path = "e:/code/projects/abhiHub/abhihub/abhi-hub/methods/supabase_helper.py"
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    helpers = """

def toggle_like(user_id: str, document_id: str) -> dict:
    client = init_supabase()
    if not client: return {"success": False, "message": "Failed to init supabase"}
    try:
        # Check if vote exists
        existing = client.table('document_votes').select('*').eq('document_id', document_id).eq('user_id', user_id).execute()
        if existing.data:
            # Unlike
            client.table('document_votes').delete().eq('document_id', document_id).eq('user_id', user_id).execute()
            # Decrement document count
            res = client.table('documents').select('like_count').eq('id', document_id).single().execute()
            if res.data:
                count = max(0, res.data.get('like_count', 0) - 1)
                client.table('documents').update({'like_count': count}).eq('id', document_id).execute()
            return {"success": True, "action": "unliked", "like_count": count}
        else:
            # Like
            client.table('document_votes').insert({
                'document_id': document_id,
                'user_id': user_id,
                'vote': 'upvote'
            }).execute()
            # Increment document count
            res = client.table('documents').select('like_count').eq('id', document_id).single().execute()
            if res.data:
                count = res.data.get('like_count', 0) + 1
                client.table('documents').update({'like_count': count}).eq('id', document_id).execute()
            return {"success": True, "action": "liked", "like_count": count}
    except Exception as e:
        return {"success": False, "message": str(e)}

def toggle_bookmark(user_id: str, document_id: str) -> dict:
    client = init_supabase()
    if not client: return {"success": False, "message": "Failed to init supabase"}
    try:
        # Check if bookmark exists
        existing = client.table('bookmarks').select('*').eq('document_id', document_id).eq('user_id', user_id).execute()
        if existing.data:
            # Unbookmark
            client.table('bookmarks').delete().eq('document_id', document_id).eq('user_id', user_id).execute()
            # Decrement document count
            res = client.table('documents').select('bookmark_count').eq('id', document_id).single().execute()
            if res.data:
                count = max(0, res.data.get('bookmark_count', 0) - 1)
                client.table('documents').update({'bookmark_count': count}).eq('id', document_id).execute()
            return {"success": True, "action": "unbookmarked", "bookmark_count": count}
        else:
            # Bookmark
            client.table('bookmarks').insert({
                'document_id': document_id,
                'user_id': user_id
            }).execute()
            # Increment document count
            res = client.table('documents').select('bookmark_count').eq('id', document_id).single().execute()
            if res.data:
                count = res.data.get('bookmark_count', 0) + 1
                client.table('documents').update({'bookmark_count': count}).eq('id', document_id).execute()
            return {"success": True, "action": "bookmarked", "bookmark_count": count}
    except Exception as e:
        return {"success": False, "message": str(e)}

def add_comment(user_id: str, document_id: str, content: str) -> dict:
    client = init_supabase()
    if not client: return {"success": False, "message": "Failed to init supabase"}
    try:
        # Insert comment
        res = client.table('document_comments').insert({
            'document_id': document_id,
            'user_id': user_id,
            'content': content
        }).execute()
        comment_data = res.data[0] if res.data else {}
        
        # Increment document count
        doc_res = client.table('documents').select('comment_count').eq('id', document_id).single().execute()
        if doc_res.data:
            count = doc_res.data.get('comment_count', 0) + 1
            client.table('documents').update({'comment_count': count}).eq('id', document_id).execute()
        
        return {"success": True, "comment": comment_data}
    except Exception as e:
        return {"success": False, "message": str(e)}

def get_comments(document_id: str) -> dict:
    client = init_supabase()
    if not client: return {"success": False, "message": "Failed to init supabase"}
    try:
        res = client.table('document_comments')\\
            .select('*, profiles(full_name, email)')\\
            .eq('document_id', document_id)\\
            .eq('is_deleted', False)\\
            .order('created_at', desc=False)\\
            .execute()
        return {"success": True, "comments": res.data if res.data else []}
    except Exception as e:
        return {"success": False, "message": str(e)}
"""
    if "def toggle_like" not in content:
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(helpers)

if __name__ == "__main__":
    append_supabase_helpers()
