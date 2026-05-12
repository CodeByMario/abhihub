"""
Models for notifications and push subscriptions.
Maps to abhihub.notifications, abhihub.push_subscriptions.
"""

from typing import Dict, List
from data.db import get_client


class Notification:
    """abhihub.notifications"""

    TABLE = "notifications"

    @staticmethod
    def create(
        user_id: str,
        notification_type: str,
        title: str,
        message: str,
        action_url: str = None,
    ) -> Dict:
        client = get_client()
        if not client:
            return {"success": False, "message": "No client"}
        try:
            data = {
                "user_id": user_id,
                "type": notification_type,
                "title": title,
                "message": message,
            }
            if action_url:
                data["action_url"] = action_url
            client.table(Notification.TABLE).insert(data).execute()
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @staticmethod
    def create_by_email(
        user_email: str,
        notification_type: str,
        title: str,
        message: str,
        url: str = None,
    ) -> Dict:
        """Resolve email → user_id, then create the notification."""
        if user_email == "all":
            return {"success": True, "message": "Broadcast not logged per-user"}
        from data.profiles import Profile
        uid = Profile.get_id_by_email(user_email)
        if not uid:
            return {"success": False, "message": "User not found"}
        return Notification.create(uid, notification_type, title, message, url)

    @staticmethod
    def get_history(limit: int = 10) -> List[dict]:
        client = get_client()
        if not client:
            return []
        try:
            res = (
                client.table(Notification.TABLE)
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return res.data if res.data else []
        except Exception as e:
            print(f"Error fetching notifications: {e}")
            return []

    @staticmethod
    def mark_read(notification_id: str) -> Dict:
        client = get_client()
        if not client:
            return {"success": False}
        try:
            client.table(Notification.TABLE).update({"is_read": True}).eq("id", notification_id).execute()
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}


class PushSubscription:
    """abhihub.push_subscriptions"""

    TABLE = "push_subscriptions"

    @staticmethod
    def save(
        user_id: str = None,
        user_email: str = None,
        endpoint: str = "",
        p256dh: str = "",
        auth: str = "",
        device_type: str = None,
    ) -> Dict:
        client = get_client()
        if not client:
            return {"success": False, "message": "No client"}
        try:
            uid = user_id
            if not uid and user_email:
                from data.profiles import Profile
                uid = Profile.get_id_by_email(user_email)
            if not uid:
                return {"success": False, "message": "User not found"}

            data = {
                "user_id": uid,
                "endpoint": endpoint,
                "p256dh": p256dh,
                "auth": auth,
            }
            if device_type:
                data["device_type"] = device_type
            client.table(PushSubscription.TABLE).upsert(data, on_conflict="endpoint").execute()
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @staticmethod
    def get_all() -> dict:
        client = get_client()
        if not client:
            return {}
        try:
            res = client.table(PushSubscription.TABLE).select("*, profiles(email)").execute()
            subs = {}
            for row in res.data:
                subs[row["user_id"]] = {
                    "subscription": {
                        "endpoint": row["endpoint"],
                        "keys": {
                            "p256dh": row["p256dh"],
                            "auth": row["auth"],
                        },
                    },
                    "email": (row.get("profiles") or {}).get("email", ""),
                    "created_at": row.get("created_at"),
                    "device_type": row.get("device_type"),
                }
            return subs
        except Exception as e:
            print(f"Error fetching subscriptions: {e}")
            return {}

    @staticmethod
    def remove_by_endpoint(endpoint: str) -> bool:
        client = get_client()
        if not client:
            return False
        try:
            client.table(PushSubscription.TABLE).delete().eq("endpoint", endpoint).execute()
            return True
        except Exception as e:
            print(f"Error removing subscription: {e}")
            return False
