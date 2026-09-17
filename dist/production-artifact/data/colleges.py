"""
Models for the academic hierarchy: College → Department → Subject.
Maps to abhihub.colleges, abhihub.departments, abhihub.subjects.
"""

from typing import Dict, List, Optional
from data.db import get_client, validate_uuid


class College:
    """abhihub.colleges"""

    TABLE = "colleges"

    @staticmethod
    def get_all() -> Dict:
        client = get_client()
        if not client:
            return {"success": False, "data": []}
        try:
            res = client.table(College.TABLE).select("*").order("name").execute()
            for c in res.data:
                c["short_name"] = c.get("abbreviation")
            return {"success": True, "data": res.data}
        except Exception as e:
            return {"success": False, "data": [], "message": str(e)}

    @staticmethod
    def get_by_id(college_id: str) -> Optional[dict]:
        client = get_client()
        if not client or not validate_uuid(college_id):
            return None
        try:
            res = client.table(College.TABLE).select("*").eq("id", college_id).execute()
            return res.data[0] if res.data else None
        except Exception:
            return None

    @staticmethod
    def create(name: str, abbreviation: str = None, city: str = None) -> Dict:
        client = get_client()
        if not client:
            return {"success": False, "message": "No client"}
        try:
            data = {"name": name}
            if abbreviation:
                data["abbreviation"] = abbreviation
            if city:
                data["city"] = city
            res = client.table(College.TABLE).insert(data).execute()
            return {"success": True, "data": res.data[0]} if res.data else {"success": False}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @staticmethod
    def update(college_id: str, updates: dict) -> Dict:
        client = get_client()
        if not client:
            return {"success": False, "message": "No client"}
        try:
            res = client.table(College.TABLE).update(updates).eq("id", college_id).execute()
            return {"success": True, "data": res.data[0]} if res.data else {"success": False}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @staticmethod
    def delete(college_id: str) -> Dict:
        client = get_client()
        if not client:
            return {"success": False, "message": "No client"}
        try:
            client.table(College.TABLE).delete().eq("id", college_id).execute()
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}


class Department:
    """abhihub.departments"""

    TABLE = "departments"

    @staticmethod
    def get_all() -> Dict:
        client = get_client()
        if not client:
            return {"success": False, "data": []}
        try:
            res = client.table(Department.TABLE).select("*").order("name").execute()
            for b in res.data:
                b["short_name"] = b.get("abbreviation")
                b["branch_id"] = b.get("id")
                b["branch_name"] = b.get("name")
            return {"success": True, "data": res.data}
        except Exception as e:
            return {"success": False, "data": [], "message": str(e)}

    @staticmethod
    def get_by_college(college_id: str) -> List[dict]:
        client = get_client()
        if not client or not validate_uuid(college_id):
            return []
        try:
            res = (
                client.table(Department.TABLE)
                .select("*")
                .eq("college_id", college_id)
                .order("name")
                .execute()
            )
            return res.data or []
        except Exception:
            return []

    @staticmethod
    def get_by_id(dept_id: str) -> Optional[dict]:
        client = get_client()
        if not client or not validate_uuid(dept_id):
            return None
        try:
            res = client.table(Department.TABLE).select("*").eq("id", dept_id).execute()
            return res.data[0] if res.data else None
        except Exception:
            return None

    @staticmethod
    def create(college_id: str, name: str, abbreviation: str = None) -> Dict:
        client = get_client()
        if not client:
            return {"success": False, "message": "No client"}
        try:
            data = {"college_id": college_id, "name": name}
            if abbreviation:
                data["abbreviation"] = abbreviation
            res = client.table(Department.TABLE).insert(data).execute()
            return {"success": True, "data": res.data[0]} if res.data else {"success": False}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @staticmethod
    def update(dept_id: str, updates: dict) -> Dict:
        client = get_client()
        if not client:
            return {"success": False, "message": "No client"}
        try:
            res = client.table(Department.TABLE).update(updates).eq("id", dept_id).execute()
            return {"success": True, "data": res.data[0]} if res.data else {"success": False}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @staticmethod
    def delete(dept_id: str) -> Dict:
        client = get_client()
        if not client:
            return {"success": False, "message": "No client"}
        try:
            client.table(Department.TABLE).delete().eq("id", dept_id).execute()
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}


class Subject:
    """abhihub.subjects"""

    TABLE = "subjects"

    @staticmethod
    def get_all() -> Dict:
        client = get_client()
        if not client:
            return {"success": False, "data": []}
        try:
            res = client.table(Subject.TABLE).select("*").order("name").execute()
            return {"success": True, "data": res.data}
        except Exception as e:
            return {"success": False, "data": [], "message": str(e)}

    @staticmethod
    def get_by_department(dept_id: str) -> List[dict]:
        client = get_client()
        if not client or not validate_uuid(dept_id):
            return []
        try:
            res = (
                client.table(Subject.TABLE)
                .select("*")
                .eq("department_id", dept_id)
                .order("name")
                .execute()
            )
            return res.data or []
        except Exception:
            return []

    @staticmethod
    def get_by_id(subject_id: str) -> Optional[dict]:
        client = get_client()
        if not client or not validate_uuid(subject_id):
            return None
        try:
            res = client.table(Subject.TABLE).select("*").eq("id", subject_id).execute()
            return res.data[0] if res.data else None
        except Exception:
            return None

    @staticmethod
    def search_by_name(name: str) -> Optional[dict]:
        """Return the first subject whose name matches (case-insensitive)."""
        client = get_client()
        if not client or not name:
            return None
        try:
            res = (
                client.table(Subject.TABLE)
                .select("id")
                .ilike("name", f"%{name}%")
                .limit(1)
                .execute()
            )
            return res.data[0] if res.data else None
        except Exception:
            return None

    @staticmethod
    def create(department_id: str, name: str, subject_code: str) -> Dict:
        client = get_client()
        if not client:
            return {"success": False, "message": "No client"}
        try:
            data = {
                "department_id": department_id,
                "name": name,
                "subject_code": subject_code,
            }
            res = client.table(Subject.TABLE).insert(data).execute()
            return {"success": True, "data": res.data[0]} if res.data else {"success": False}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @staticmethod
    def update(subject_id: str, updates: dict) -> Dict:
        client = get_client()
        if not client:
            return {"success": False, "message": "No client"}
        try:
            res = client.table(Subject.TABLE).update(updates).eq("id", subject_id).execute()
            return {"success": True, "data": res.data[0]} if res.data else {"success": False}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @staticmethod
    def delete(subject_id: str) -> Dict:
        client = get_client()
        if not client:
            return {"success": False, "message": "No client"}
        try:
            client.table(Subject.TABLE).delete().eq("id", subject_id).execute()
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}
