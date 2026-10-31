"""Persistent incident lifecycle and administrator notification fan-out."""

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from methods.supabase_helper import init_supabase_admin, init_supabase

log = logging.getLogger("abhihub.observability.alerts")


def _db():
    return init_supabase_admin() or init_supabase()


def _fingerprint(alert: Dict) -> str:
    parts = (
        alert.get("name", "unnamed"),
        alert.get("service", "abhihub"),
        alert.get("environment", os.getenv("FLASK_ENV", "development")),
        alert.get("route", ""),
        alert.get("severity", "medium"),
    )
    return hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()


def create_incident(alert: Dict, client=None) -> Dict:
    """Create or refresh a deduplicated incident."""
    required = ("name", "severity", "message")
    missing = [field for field in required if not str(alert.get(field, "")).strip()]
    if missing:
        return {"success": False, "error": f"Missing alert fields: {', '.join(missing)}"}

    client = client or _db()
    if client is None:
        return {"success": False, "error": "Observability database is unavailable"}

    now = datetime.now(timezone.utc).isoformat()
    fingerprint = _fingerprint(alert)
    payload = {
        "fingerprint": fingerprint,
        "name": str(alert["name"]).strip()[:160],
        "severity": str(alert["severity"]).lower().strip(),
        "service": str(alert.get("service", "abhihub")).strip()[:100],
        "environment": str(alert.get("environment", os.getenv("FLASK_ENV", "development"))).strip()[:40],
        "route": str(alert.get("route", "")).strip()[:300],
        "message": str(alert["message"]).strip()[:2000],
        "status": "firing",
        "last_seen_at": now,
        "metadata": alert.get("metadata") or {},
    }
    try:
        existing = (
            client.table("admin_alert_incidents")
            .select("*")
            .eq("fingerprint", fingerprint)
            .eq("status", "firing")
            .limit(1)
            .execute()
        )
        if existing.data:
            incident = existing.data[0]
            updated = client.table("admin_alert_incidents").update({
                "last_seen_at": now,
                "occurrence_count": int(incident.get("occurrence_count") or 1) + 1,
                "message": payload["message"],
                "metadata": payload["metadata"],
            }).eq("id", incident["id"]).execute()
            return {"success": True, "deduplicated": True, "incident": (updated.data or [incident])[0]}

        created = client.table("admin_alert_incidents").insert(payload).execute()
        if not created.data:
            return {"success": False, "error": "Incident was not created"}
        return {"success": True, "deduplicated": False, "incident": created.data[0]}
    except Exception as exc:
        log.error("incident persistence failed: %s", exc)
        return {"success": False, "error": "Incident persistence failed"}


def notify_administrators(incident: Dict, client=None) -> Dict:
    """Deliver an incident to every active admin using in-app and Web Push channels."""
    client = client or _db()
    if client is None:
        return {"success": False, "error": "Observability database is unavailable", "sent": 0}
    try:
        admins = (
            client.table("profiles")
            .select("id,email,role,is_admin")
            .eq("is_deleted", False)
            .execute()
        ).data or []
    except Exception as exc:
        log.error("admin lookup failed: %s", exc)
        return {"success": False, "error": "Administrator lookup failed", "sent": 0}

    admins = [
        admin for admin in admins
        if (admin.get("is_admin") or str(admin.get("role", "")).lower() in ("admin", "superadmin"))
    ]
    title = f"[{str(incident.get('severity', 'medium')).upper()}] {incident.get('name', 'System alert')}"
    body = str(incident.get("message", "A system alert requires attention"))[:500]
    sent = 0
    failures = 0
    for admin in admins:
        admin_id = admin.get("id")
        delivery = {"incident_id": incident.get("id"), "admin_id": admin_id, "channel": "in_app", "status": "failed"}
        try:
            from data.notifications import Notification
            result = Notification.create(admin_id, "system", title, body, "/admin/observability/incidents")
            if result.get("success"):
                delivery["status"] = "sent"
                sent += 1
            else:
                failures += 1
            client.table("admin_alert_deliveries").insert(delivery).execute()
        except Exception as exc:
            failures += 1
            log.error("admin alert delivery failed for %s: %s", admin_id, exc)
        try:
            from push_notifications import send_notification
            push_result = send_notification(
                admin_id,
                title,
                body,
                url="/admin/observability/incidents",
                tag=f"incident-{incident.get('id', 'unknown')}",
                category="system",
                dedupe_key=f"incident:{incident.get('id')}",
            )
            client.table("admin_alert_deliveries").insert({
                "incident_id": incident.get("id"),
                "admin_id": admin_id,
                "channel": "push",
                "status": "sent" if push_result.get("success") else "failed",
                "error_message": push_result.get("error"),
            }).execute()
        except Exception as exc:
            failures += 1
            log.error("admin push delivery failed for %s: %s", admin_id, exc)
    return {"success": failures == 0, "sent": sent, "failed": failures, "admins": len(admins)}


def list_incidents(status: Optional[str] = None, limit: int = 50, client=None) -> Dict:
    client = client or _db()
    if client is None:
        return {"success": False, "error": "Observability database is unavailable"}
    try:
        query = client.table("admin_alert_incidents").select("*").order("last_seen_at", desc=True).limit(min(limit, 100))
        if status:
            query = query.eq("status", status)
        return {"success": True, "incidents": query.execute().data or []}
    except Exception as exc:
        log.error("incident listing failed: %s", exc)
        return {"success": False, "error": "Incident listing failed"}


def get_incident(incident_id: str, client=None) -> Dict:
    client = client or _db()
    if client is None:
        return {"success": False, "error": "Observability database is unavailable"}
    try:
        result = client.table("admin_alert_incidents").select("*").eq("id", incident_id).limit(1).execute()
        if not result.data:
            return {"success": False, "error": "Incident not found"}
        deliveries = (
            client.table("admin_alert_deliveries")
            .select("*")
            .eq("incident_id", incident_id)
            .order("sent_at", desc=True)
            .limit(100)
            .execute()
        )
        incident = dict(result.data[0])
        incident["deliveries"] = deliveries.data or []
        return {"success": True, "incident": incident}
    except Exception as exc:
        log.error("incident detail lookup failed: %s", exc)
        return {"success": False, "error": "Incident detail lookup failed"}


def create_silence(incident_id: str, admin_id: str, duration_minutes: int, reason: str, client=None) -> Dict:
    if duration_minutes < 1 or duration_minutes > 10080:
        return {"success": False, "error": "Silence duration must be between 1 and 10080 minutes"}
    client = client or _db()
    if client is None:
        return {"success": False, "error": "Observability database is unavailable"}
    from datetime import timedelta
    try:
        result = client.table("admin_alert_silences").insert({
            "incident_id": incident_id,
            "created_by": admin_id,
            "reason": (reason or "Maintenance")[:500],
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)).isoformat(),
        }).execute()
        if not result.data:
            return {"success": False, "error": "Silence was not created"}
        return {"success": True, "silence": result.data[0]}
    except Exception as exc:
        log.error("incident silence failed: %s", exc)
        return {"success": False, "error": "Incident silence failed"}


def update_incident_status(incident_id: str, status: str, admin_id: str, note: str = "", client=None) -> Dict:
    if status not in ("acknowledged", "resolved"):
        return {"success": False, "error": "Invalid incident status"}
    client = client or _db()
    if client is None:
        return {"success": False, "error": "Observability database is unavailable"}
    field = "acknowledged_at" if status == "acknowledged" else "resolved_at"
    try:
        result = client.table("admin_alert_incidents").update({
            "status": status,
            field: datetime.now(timezone.utc).isoformat(),
            "acknowledged_by": admin_id,
            "resolution_note": note[:2000],
        }).eq("id", incident_id).execute()
        if not result.data:
            return {"success": False, "error": "Incident not found"}
        return {"success": True, "incident": result.data[0]}
    except Exception as exc:
        log.error("incident status update failed: %s", exc)
        return {"success": False, "error": "Incident status update failed"}
