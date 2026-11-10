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


def diagnose_service_health(feature: str = "upload") -> Dict:
    """Check health and connectivity of all infrastructure services related to the feature."""
    import time
    health = {
        "database": {"name": "Supabase DB", "status": "unknown"},
        "cloud_storage": {"name": "Cloudinary", "status": "unknown"},
        "api_keys": {"status": "ok", "configured": [], "missing": []}
    }
    required_keys = ["SUPABASE_URL", "SUPABASE_KEY"]
    if feature in ("upload", "file_open"):
        required_keys.extend(["CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"])
    for k in required_keys:
        if os.getenv(k):
            health["api_keys"]["configured"].append(k)
        else:
            health["api_keys"]["missing"].append(k)
    if health["api_keys"]["missing"]:
        health["api_keys"]["status"] = "missing_keys"

    t0 = time.time()
    try:
        sb = _db()
        if sb:
            sb.table("profiles").select("id").limit(1).execute()
            health["database"] = {"name": "Supabase DB", "status": "ok", "latency_ms": round((time.time() - t0) * 1000)}
        else:
            health["database"] = {"name": "Supabase DB", "status": "error", "error": "Client unavailable"}
    except Exception as db_err:
        health["database"] = {"name": "Supabase DB", "status": "error", "error": str(db_err)[:120], "latency_ms": round((time.time() - t0) * 1000)}

    t0 = time.time()
    try:
        import cloudinary.api
        cloudinary.api.ping()
        health["cloud_storage"] = {"name": "Cloudinary", "status": "ok", "latency_ms": round((time.time() - t0) * 1000)}
    except Exception as cld_err:
        health["cloud_storage"] = {"name": "Cloudinary", "status": "error", "error": str(cld_err)[:120], "latency_ms": round((time.time() - t0) * 1000)}

    return health


def report_critical_incident(
    name: str,
    message: str,
    route: str = "",
    cause: Optional[str] = None,
    account: Optional[Dict] = None,
    feature: str = "upload",
    metadata: Optional[Dict] = None
) -> Dict:
    """Record a detailed critical incident with root cause, affected account, and service health snapshot."""
    try:
        account_info = dict(account or {})
        try:
            from flask import session, request
            if not account_info and session:
                user = session.get("user") or {}
                profile = session.get("profile") or {}
                account_info = {
                    "uid": user.get("uid") or user.get("id") or "anonymous",
                    "email": user.get("email") or "unknown",
                    "role": user.get("role") or profile.get("role") or "student"
                }
            if request and hasattr(request, "remote_addr") and "ip" not in account_info:
                account_info["ip"] = request.remote_addr
            if not route and request and hasattr(request, "path"):
                route = request.path
        except Exception:
            pass

        service_health = diagnose_service_health(feature)

        detailed_report = {
            "root_cause": cause or message,
            "affected_account": account_info,
            "feature": feature,
            "service_health": service_health,
            "route": route,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        meta = dict(metadata or {})
        meta["detailed_report"] = detailed_report

        user_tag = account_info.get("email") or account_info.get("uid") or "anonymous"
        db_st = service_health["database"]["status"]
        st_st = service_health["cloud_storage"]["status"]
        key_st = service_health["api_keys"]["status"]

        full_message = (
            f"{message} | Cause: {cause or 'Unknown'} | Account: {user_tag} "
            f"| Health: DB={db_st}, Storage={st_st}, Keys={key_st}"
        )[:2000]

        incident_res = create_incident({
            "name": name,
            "severity": "critical",
            "message": full_message,
            "route": route,
            "metadata": meta
        })
        if incident_res.get("success") and incident_res.get("incident"):
            import threading
            threading.Thread(target=notify_administrators, args=(incident_res["incident"],), daemon=True).start()
        return incident_res
    except Exception as exc:
        log.error("report_critical_incident failed: %s", exc)
        return {"success": False, "error": str(exc)}


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
