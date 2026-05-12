"""
Models for user-related tables: Profile, Student, Teacher, UserSession.
Maps to abhihub.profiles, abhihub.students, abhihub.teachers, abhihub.user_sessions.
"""

from typing import Dict, Optional
from data.db import get_client, validate_uuid


class Profile:
    """abhihub.profiles"""

    TABLE = "profiles"

    @staticmethod
    def get_by_id(user_id: str) -> Optional[dict]:
        client = get_client()
        if not client or not validate_uuid(user_id):
            return None
        try:
            res = client.table(Profile.TABLE).select("*").eq("id", user_id).execute()
            return res.data[0] if res.data else None
        except Exception:
            return None

    @staticmethod
    def get_by_email(email: str) -> Optional[dict]:
        client = get_client()
        if not client or not email:
            return None
        try:
            res = client.table(Profile.TABLE).select("*").eq("email", email).execute()
            return res.data[0] if res.data else None
        except Exception:
            return None

    @staticmethod
    def get_id_by_email(email: str) -> Optional[str]:
        """Quick lookup: email → profile UUID."""
        client = get_client()
        if not client or not email:
            return None
        try:
            res = client.table(Profile.TABLE).select("id").eq("email", email).execute()
            return res.data[0]["id"] if res.data else None
        except Exception:
            return None

    @staticmethod
    def upsert(user_id: str, email: str, full_name: str,
               role: str = "student", college_id: str = None,
               department_id: str = None) -> Dict:
        client = get_client()
        if not client:
            return {"success": False, "message": "No client"}
        try:
            data = {
                "id": user_id,
                "role": role,
                "email": email,
                "full_name": full_name,
                "college_id": college_id if validate_uuid(college_id) else None,
                "department_id": department_id if validate_uuid(department_id) else None,
            }
            client.table(Profile.TABLE).upsert(data).execute()
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @staticmethod
    def is_admin_or_mod(user_id: str) -> bool:
        profile = Profile.get_by_id(user_id)
        if not profile:
            return False
        return profile.get("role") in ("admin", "moderator")


class Student:
    """abhihub.students"""

    TABLE = "students"

    @staticmethod
    def get_profile(user_id: str) -> Dict:
        client = get_client()
        if not client:
            return {"success": False, "data": None}
        try:
            res = (
                client.table(Student.TABLE)
                .select("*, profiles(*), colleges(*), departments(*)")
                .eq("profile_id", user_id)
                .execute()
            )
            if res.data:
                return {"success": True, "data": res.data[0]}
            return {"success": True, "data": None, "message": "Not found"}
        except Exception as e:
            return {"success": False, "data": None, "message": str(e)}

    @staticmethod
    def create_or_update(user_id: str, profile_data: dict) -> Dict:
        """Upsert both profiles and students rows in one go."""
        client = get_client()
        if not client:
            return {"success": False}
        try:
            b_id = profile_data.get("branch_id")
            role = profile_data.get("user_role", "student")

            Profile.upsert(
                user_id=user_id,
                email=profile_data.get("student_email", ""),
                full_name=profile_data.get("student_name", ""),
                role=role,
                college_id=profile_data.get("college_id"),
                department_id=b_id if validate_uuid(b_id) else None,
            )

            if role == "student":
                client.table(Student.TABLE).upsert({
                    "profile_id": user_id,
                    "registration_number": profile_data.get("registration_number"),
                    "pursuing_year": profile_data.get("pursuing_year"),
                    "year_of_joining": profile_data.get("year_of_joining"),
                    "profile_completed": True,
                }).execute()
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @staticmethod
    def check_completed(user_id: str) -> bool:
        client = get_client()
        if not client:
            return False
        try:
            res = (
                client.table(Student.TABLE)
                .select("profile_completed")
                .eq("profile_id", user_id)
                .execute()
            )
            if res.data:
                return res.data[0].get("profile_completed", False)
            return False
        except Exception:
            return False


class Teacher:
    """abhihub.teachers"""

    TABLE = "teachers"

    @staticmethod
    def get_profile(user_id: str) -> Dict:
        client = get_client()
        if not client:
            return {"success": False, "data": None}
        try:
            res = (
                client.table(Teacher.TABLE)
                .select("*, profiles(*)")
                .eq("profile_id", user_id)
                .execute()
            )
            if res.data:
                return {"success": True, "data": res.data[0]}
            return {"success": True, "data": None, "message": "Not found"}
        except Exception as e:
            return {"success": False, "data": None, "message": str(e)}

    @staticmethod
    def create_or_update(user_id: str, employee_id: str = None,
                         designation: str = None) -> Dict:
        client = get_client()
        if not client:
            return {"success": False}
        try:
            data = {"profile_id": user_id, "profile_completed": True}
            if employee_id:
                data["employee_id"] = employee_id
            if designation:
                data["designation"] = designation
            client.table(Teacher.TABLE).upsert(data).execute()
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}


class UserSession:
    """abhihub.user_sessions"""

    TABLE = "user_sessions"

    @staticmethod
    def log_login(user_id: str, ip_address: str = None,
                  user_agent: str = None, device_type: str = None) -> Dict:
        client = get_client()
        if not client:
            return {"success": False}
        try:
            data = {"user_id": user_id}
            if ip_address:
                data["ip_address"] = ip_address
            if user_agent:
                data["user_agent"] = user_agent
            if device_type:
                data["device_type"] = device_type
            res = client.table(UserSession.TABLE).insert(data).execute()
            return {"success": True, "session_id": res.data[0]["id"]} if res.data else {"success": False}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @staticmethod
    def log_logout(session_id: str, duration_minutes: int = None) -> Dict:
        client = get_client()
        if not client:
            return {"success": False}
        try:
            from datetime import datetime, timezone
            updates = {"logout_time": datetime.now(timezone.utc).isoformat()}
            if duration_minutes is not None:
                updates["duration_minutes"] = duration_minutes
            client.table(UserSession.TABLE).update(updates).eq("id", session_id).execute()
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}
