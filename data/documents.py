"""
Model for the documents table and related operations.
Maps to abhihub.documents.
"""

import json
from typing import Dict, List, Optional
from data.db import get_client, validate_uuid, format_file_size
import logging


class Document:
    """abhihub.documents"""

    TABLE = "documents"

    # ── Serialisation ───────────────────────────────────────────────

    @staticmethod
    def to_json(doc: dict, current_user_id: str = None) -> dict:
        """Convert a raw Supabase document row into the app's JSON format."""
        title = doc.get("title", "Untitled")
        url = doc.get("file_url", "")
        doc_type = doc.get("document_category", "Other")

        prof = doc.get("profiles") or {}
        author = prof.get("full_name", "Unknown")
        author_email = prof.get("email", "")

        subj_data = doc.get("subjects") or {}
        subject = subj_data.get("name", "General")
        year = ""

        desc_str = doc.get("description") or "{}"
        try:
            if desc_str.startswith("{"):
                desc = json.loads(desc_str)
                if not subj_data:
                    subject = desc.get("subject", subject)
                year = desc.get("year", "")
            else:
                if "Year:" in desc_str:
                    year = desc_str.split("Year:")[1].split("|")[0].strip()
        except Exception:
            pass

        file_path = f"Documents/{author}/{doc_type}/{year}/{subject}/{title}"

        is_liked = False
        is_bookmarked = False
        if current_user_id:
            if isinstance(doc.get("document_votes"), list):
                is_liked = any(
                    str(v.get("user_id")) == str(current_user_id)
                    for v in doc["document_votes"]
                )
            if isinstance(doc.get("bookmarks"), list):
                is_bookmarked = any(
                    str(b.get("user_id")) == str(current_user_id)
                    for b in doc["bookmarks"]
                )

        return {
            "file-name": title,
            "file-type": doc.get("file_type", "pdf"),
            "file-path": file_path,
            "url": url,
            "type": doc_type,
            "subject": subject,
            "year": str(year),
            "author": author,
            "author_email": author_email,
            "date": doc.get("created_at", "")[:10] if doc.get("created_at") else "",
            "size": format_file_size(doc.get("file_size_bytes") or 0),
            "cloudinary_id": doc.get("provider_public_id", ""),
            "source": doc.get("storage_provider", "unknown"),
            "verified": doc.get("status") == "approved",
            "record_id": doc.get("id", ""),
            "view_count": doc.get("view_count", 0),
            "like_count": doc.get("like_count", 0),
            "comment_count": doc.get("comment_count", 0),
            "bookmark_count": doc.get("bookmark_count", 0),
            "is_liked": is_liked,
            "is_bookmarked": is_bookmarked,
        }

    # ── Queries ─────────────────────────────────────────────────────

    @staticmethod
    def get_all_approved(current_user_id: str = None) -> Dict:
        """Fetch all approved documents (with joins) and serialise to JSON."""
        client = get_client()
        if not client:
            return {"success": False, "data": [], "count": 0}
        try:
            res = (
                client.table(Document.TABLE)
                .select(
                    "*, profiles(full_name, email), subjects(name), "
                    "document_votes(user_id), bookmarks(user_id)"
                )
                .eq("status", "approved")
                .order("created_at", desc=True)
                .execute()
            )
            files = [Document.to_json(d, current_user_id) for d in res.data] if res.data else []
            return {"success": True, "data": files, "count": len(files)}
        except Exception as e:
            return {"success": False, "data": [], "count": 0, "message": str(e)}

    @staticmethod
    def search(
        query: str = "",
        document_type: str = None,
        college_id: str = None,
        department_id: str = None,
        year: str = None,
        limit: int = 50,
    ) -> List[dict]:
        client = get_client()
        if not client:
            return []
        try:
            q = client.table(Document.TABLE).select(
                "*, profiles(full_name, email), subjects(name)"
            )
            if document_type:
                q = q.eq("document_category", document_type)
            if college_id and validate_uuid(college_id):
                q = q.eq("college_id", college_id)
            if department_id and validate_uuid(department_id):
                q = q.eq("department_id", department_id)
            if query:
                q = q.or_(f"title.ilike.%{query}%,description.ilike.%{query}%")
            res = q.order("created_at", desc=True).limit(limit).execute()
            return res.data if res.data else []
        except Exception:
            return []

    @staticmethod
    def get_by_uploader(user_id: str = None, user_email: str = None,
                        limit: int = 20) -> Dict:
        """Fetch documents uploaded by a user (by ID or email)."""
        client = get_client()
        if not client:
            return {"success": False, "data": []}
        try:
            uid = user_id
            if not uid and user_email:
                from data.profiles import Profile
                uid = Profile.get_id_by_email(user_email)
            if not uid:
                return {"success": True, "data": []}

            res = (
                client.table(Document.TABLE)
                .select("*, profiles(full_name, email), subjects(name)")
                .eq("uploader_id", uid)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return {"success": True, "data": res.data or [], "count": len(res.data) if res.data else 0}
        except Exception as e:
            return {"success": False, "data": [], "message": str(e)}

    @staticmethod
    def get_all(limit: int = 100, offset: int = 0) -> Dict:
        client = get_client()
        if not client:
            return {"success": False, "data": [], "total": 0}
        try:
            res = (
                client.table(Document.TABLE)
                .select("*", count="exact")
                .range(offset, offset + limit - 1)
                .execute()
            )
            return {
                "success": True,
                "data": res.data,
                "total": getattr(res, "count", 0),
                "limit": limit,
                "offset": offset,
            }
        except Exception as e:
            return {"success": False, "data": [], "total": 0, "message": str(e)}

    # ── Mutations ───────────────────────────────────────────────────

    @staticmethod
    def create(
        uploader_id: str,
        file_name: str,
        file_url: str,
        file_type: str,
        file_size: int,
        document_category: str,
        storage_provider: str = "cloudinary",
        provider_public_id: str = None,
        subject_name: str = None,
        year: str = "",
        college_id: str = None,
        department_id: str = None,
    ) -> Dict:
        client = get_client()
        if not client:
            return {"success": False, "message": "No client"}
        try:
            c_id = college_id if validate_uuid(college_id) else None
            d_id = department_id if validate_uuid(department_id) else None
            u_id = uploader_id if validate_uuid(uploader_id) else None

            sub_id = None
            if subject_name:
                from data.colleges import Subject
                sub = Subject.search_by_name(subject_name)
                if sub:
                    sub_id = sub["id"]

            desc = json.dumps({"subject": subject_name, "year": year})

            data = {
                "uploader_id": u_id,
                "college_id": c_id,
                "department_id": d_id,
                "subject_id": sub_id,
                "title": file_name,
                "document_category": document_category or "Notes",
                "description": desc,
                "file_url": file_url,
                "storage_provider": storage_provider,
                "provider_public_id": provider_public_id,
                "file_type": file_type,
                "file_size_bytes": file_size,
                "status": "pending",
            }
            res = client.table(Document.TABLE).insert(data).execute()
            if res.data:
                return {"success": True, "message": "Saved", "data": res.data[0]}
            return {"success": False, "message": "Failed"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @staticmethod
    def delete(record_id: str, uploader_id: str) -> Dict:
        client = get_client()
        if not client:
            return {"success": False}
        try:
            res = (
                client.table(Document.TABLE)
                .delete()
                .eq("id", record_id)
                .eq("uploader_id", uploader_id)
                .execute()
            )
            return {"success": True} if res.data else {"success": False}
        except Exception:
            return {"success": False}

    @staticmethod
    def update_metadata(file_path: str, update_data: dict) -> Dict:
        """Match a document by file_url and apply metadata updates."""
        client = get_client()
        if not client:
            return {"success": False, "message": "No client"}
        try:
            res = (
                client.table(Document.TABLE)
                .select("id, description")
                .ilike("file_url", f"%{file_path}%")
                .limit(1)
                .execute()
            )
            if not res.data:
                return {"success": False, "message": "File not found"}

            doc_id = res.data[0]["id"]
            try:
                desc = json.loads(res.data[0].get("description") or "{}")
            except Exception:
                desc = {}

            updates = {}
            if "file-name" in update_data:
                updates["title"] = update_data["file-name"]
            if "file-type" in update_data:
                updates["file_type"] = update_data["file-type"]
            if "type" in update_data:
                updates["document_category"] = update_data["type"]
            if "subject" in update_data:
                desc["subject"] = update_data["subject"]
            if "year" in update_data:
                desc["year"] = update_data["year"]
            if "exam" in update_data:
                desc["exam"] = update_data["exam"]

            updates["description"] = json.dumps(desc)
            client.table(Document.TABLE).update(updates).eq("id", doc_id).execute()
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ── Ranking ─────────────────────────────────────────────────────

    @staticmethod
    def calculate_ranks() -> List[dict]:
        """Calculate author leaderboard from approved documents."""
        client = get_client()
        if not client:
            return []
        try:
            res = (
                client.table(Document.TABLE)
                .select("uploader_id, document_category, description, title")
                .eq("status", "approved")
                .execute()
            )
            points_map: dict = {}
            for doc in res.data:
                author = None
                desc_str = doc.get("description")
                if desc_str:
                    try:
                        author = json.loads(desc_str).get("author")
                    except Exception:
                        pass
                if not author:
                    continue
                if author not in points_map:
                    points_map[author] = 0

                cat = doc.get("document_category", "").lower()
                if cat in ("notes", "imp questions"):
                    points_map[author] += 3
                elif cat in ("pyq", "papers", "paper"):
                    points_map[author] += 1
                else:
                    points_map[author] += 0.5

            rank_list = [{"author": k, "points": v} for k, v in points_map.items()]
            rank_list.sort(key=lambda x: x["points"], reverse=True)
            return rank_list
        except Exception as e:
            logging.error(f"Error calculating ranks: {e}")
            return []
