"""
Models for user–document interactions: Votes, Bookmarks, Comments.
Maps to abhihub.document_votes, abhihub.bookmarks, abhihub.document_comments.
"""

from typing import Dict, List
from data.db import get_client, validate_uuid


class Vote:
    """abhihub.document_votes"""

    TABLE = "document_votes"

    @staticmethod
    def toggle_like(user_id: str, document_id: str) -> Dict:
        """Like or unlike a document. Returns new state and count."""
        client = get_client()
        if not client:
            return {"success": False, "message": "No client"}
        try:
            vote_res = (
                client.table(Vote.TABLE)
                .select("*")
                .eq("document_id", document_id)
                .eq("user_id", user_id)
                .execute()
            )
            if vote_res.data:
                # Unlike
                client.table(Vote.TABLE).delete().eq("document_id", document_id).eq("user_id", user_id).execute()
                doc_res = client.table("documents").select("like_count").eq("id", document_id).execute()
                count = max(0, (doc_res.data[0]["like_count"] or 0) - 1)
                client.table("documents").update({"like_count": count}).eq("id", document_id).execute()
                return {"success": True, "is_liked": False, "like_count": count}
            else:
                # Like
                client.table(Vote.TABLE).insert({
                    "document_id": document_id,
                    "user_id": user_id,
                    "vote_type": "like",
                }).execute()
                doc_res = client.table("documents").select("like_count").eq("id", document_id).execute()
                count = (doc_res.data[0]["like_count"] or 0) + 1
                client.table("documents").update({"like_count": count}).eq("id", document_id).execute()
                return {"success": True, "is_liked": True, "like_count": count}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @staticmethod
    def toggle_like_by_email(user_email: str, document_id: str) -> Dict:
        """Convenience wrapper that resolves email → user_id first."""
        from data.profiles import Profile
        uid = Profile.get_id_by_email(user_email)
        if not uid:
            return {"success": False, "message": "User not found"}
        return Vote.toggle_like(uid, document_id)


class Bookmark:
    """abhihub.bookmarks"""

    TABLE = "bookmarks"

    @staticmethod
    def toggle(user_id: str, document_id: str) -> Dict:
        """Add or remove a bookmark. Returns new state and count."""
        client = get_client()
        if not client:
            return {"success": False, "message": "No client"}
        try:
            check = (
                client.table(Bookmark.TABLE)
                .select("*")
                .eq("document_id", document_id)
                .eq("user_id", user_id)
                .execute()
            )
            if check.data:
                # Remove bookmark
                client.table(Bookmark.TABLE).delete().eq("document_id", document_id).eq("user_id", user_id).execute()
                doc_res = client.table("documents").select("bookmark_count").eq("id", document_id).execute()
                count = max(0, (doc_res.data[0]["bookmark_count"] or 0) - 1)
                client.table("documents").update({"bookmark_count": count}).eq("id", document_id).execute()
                return {"success": True, "is_bookmarked": False, "bookmark_count": count}
            else:
                # Add bookmark
                client.table(Bookmark.TABLE).insert({
                    "document_id": document_id,
                    "user_id": user_id,
                }).execute()
                doc_res = client.table("documents").select("bookmark_count").eq("id", document_id).execute()
                count = (doc_res.data[0]["bookmark_count"] or 0) + 1
                client.table("documents").update({"bookmark_count": count}).eq("id", document_id).execute()
                return {"success": True, "is_bookmarked": True, "bookmark_count": count}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @staticmethod
    def toggle_by_email(user_email: str, document_id: str) -> Dict:
        """Convenience wrapper that resolves email → user_id first."""
        from data.profiles import Profile
        uid = Profile.get_id_by_email(user_email)
        if not uid:
            return {"success": False, "message": "User not found"}
        return Bookmark.toggle(uid, document_id)


class Comment:
    """abhihub.document_comments"""

    TABLE = "document_comments"

    @staticmethod
    def add(user_id: str, document_id: str, content: str,
            full_name: str = "", role: str = "") -> Dict:
        client = get_client()
        if not client:
            return {"success": False, "message": "No client"}
        try:
            res = client.table(Comment.TABLE).insert({
                "document_id": document_id,
                "user_id": user_id,
                "content": content,
            }).execute()

            if res.data:
                return {
                    "success": True,
                    "comment": {
                        "id": res.data[0]["id"],
                        "content": res.data[0]["content"],
                        "created_at": res.data[0]["created_at"],
                        "user_id": user_id,
                        "profiles": {
                            "full_name": full_name,
                            "role": role,
                        },
                    },
                }
            return {"success": False, "message": "Failed"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @staticmethod
    def add_by_email(user_email: str, document_id: str, content: str) -> Dict:
        """Resolve email, fetch name/role, then add the comment."""
        client = get_client()
        if not client:
            return {"success": False, "message": "No client"}
        try:
            from data.profiles import Profile
            p_res = client.table(Profile.TABLE).select("id, full_name, role").eq("email", user_email).execute()
            if not p_res.data:
                return {"success": False, "message": "User not found"}
            p = p_res.data[0]
            return Comment.add(p["id"], document_id, content, p.get("full_name", ""), p.get("role", ""))
        except Exception as e:
            return {"success": False, "message": str(e)}

    @staticmethod
    def get_for_document(document_id: str) -> Dict:
        client = get_client()
        if not client:
            return {"success": False, "data": []}
        try:
            res = (
                client.table(Comment.TABLE)
                .select("id, content, created_at, user_id, profiles(full_name, role)")
                .eq("document_id", document_id)
                .eq("is_deleted", False)
                .order("created_at", desc=False)
                .execute()
            )
            return {"success": True, "data": res.data if res.data else []}
        except Exception as e:
            return {"success": False, "data": [], "message": str(e)}


class DocumentView:
    """abhihub.document_views - Log every document view for history tracking."""

    TABLE = "document_views"

    @staticmethod
    def log_view(user_id: str, document_id: str, ip_address: str = "", device_type: str = "") -> Dict:
        """
        Log a document view by a user.
        
        Args:
            user_id: UUID of the user viewing the document
            document_id: UUID of the document being viewed
            ip_address: Optional IP address of the user
            device_type: Optional device type (desktop, mobile, tablet)
        
        Returns:
            Dict with success status and view record
        """
        client = get_client()
        if not client:
            return {"success": False, "message": "No client"}
        
        # Validate UUIDs
        if not validate_uuid(user_id) or not validate_uuid(document_id):
            return {"success": False, "message": "Invalid user_id or document_id"}
        
        try:
            res = client.table(DocumentView.TABLE).insert({
                "document_id": document_id,
                "user_id": user_id,
                "ip_address": ip_address or None,
                "device_type": device_type or None,
            }).execute()

            if res.data:
                return {
                    "success": True,
                    "view": {
                        "id": res.data[0]["id"],
                        "document_id": res.data[0]["document_id"],
                        "user_id": res.data[0]["user_id"],
                        "accessed_at": res.data[0]["accessed_at"],
                    },
                }
            return {"success": False, "message": "Failed to log view"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @staticmethod
    def log_view_by_email(user_email: str, document_id: str, ip_address: str = "", device_type: str = "") -> Dict:
        """
        Log a document view by user email (convenience wrapper).
        Resolves email to user_id first.
        """
        from data.profiles import Profile
        
        uid = Profile.get_id_by_email(user_email)
        if not uid:
            return {"success": False, "message": "User not found"}
        
        return DocumentView.log_view(uid, document_id, ip_address, device_type)

    @staticmethod
    def get_recent_for_user(user_id: str, limit: int = 20) -> Dict:
        """
        Get recent documents accessed by a user.
        
        Args:
            user_id: UUID of the user
            limit: Maximum number of records to return (default 20)
        
        Returns:
            Dict with list of recently accessed documents
        """
        client = get_client()
        if not client:
            return {"success": False, "data": []}
        
        if not validate_uuid(user_id):
            return {"success": False, "data": [], "message": "Invalid user_id"}
        
        try:
            res = (
                client.table(DocumentView.TABLE)
                .select("id, document_id, accessed_at, documents(id, title, subject_id, uploader_id, file_url, document_category)")
                .eq("user_id", user_id)
                .order("accessed_at", desc=True)
                .limit(limit)
                .execute()
            )
            
            if res.data:
                # Transform to include document details
                documents = []
                seen = set()
                for view in res.data:
                    if view["documents"] and view["documents"]["id"] not in seen:
                        seen.add(view["documents"]["id"])
                        documents.append({
                            "view_id": view["id"],
                            "accessed_at": view["accessed_at"],
                            "document": view["documents"]
                        })
                
                return {"success": True, "data": documents, "count": len(documents)}
            
            return {"success": True, "data": [], "count": 0}
        except Exception as e:
            return {"success": False, "data": [], "message": str(e)}

    @staticmethod
    def get_recent_for_user_by_email(user_email: str, limit: int = 20) -> Dict:
        """
        Get recent documents by user email (convenience wrapper).
        """
        from data.profiles import Profile
        
        uid = Profile.get_id_by_email(user_email)
        if not uid:
            return {"success": False, "data": [], "message": "User not found"}
        
        return DocumentView.get_recent_for_user(uid, limit)
