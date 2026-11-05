"""
Models for analytics and security auditing.
Maps to abhihub.document_views, abhihub.security_audit_logs.
"""

from typing import Dict
from data.db import get_client


class DocumentView:
    """abhihub.document_views"""

    TABLE = "document_views"

    @staticmethod
    def log_view(
        document_id: str,
        user_id: str = None,
        ip_address: str = None,
        device_type: str = None,
    ) -> Dict:
        from data.interactions import DocumentView as InteractionDocView
        return InteractionDocView.log_view(
            user_id=user_id or "",
            document_id=document_id or "",
            ip_address=ip_address or "",
            device_type=device_type or ""
        )


class SecurityAuditLog:
    """abhihub.security_audit_logs"""

    TABLE = "security_audit_logs"

    @staticmethod
    def log_event(
        event_type: str,
        ip_address: str = None,
        user_agent: str = None,
        user_id: str = None,
        user_email: str = None,
        document_id: str = None,
        metadata: dict = None,
    ) -> Dict:
        """
        Log a security event. Pass either *user_id* directly or *user_email*
        to resolve it automatically.
        """
        client = get_client()
        if not client:
            return {"success": False, "message": "No client"}
        try:
            uid = user_id
            if not uid and user_email and user_email != "unknown":
                from data.profiles import Profile
                uid = Profile.get_id_by_email(user_email)

            data = {
                "user_id": uid,
                "event": event_type,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "metadata": metadata or {},
            }
            if document_id:
                data["document_id"] = document_id
            client.table(SecurityAuditLog.TABLE).insert(data).execute()
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}
