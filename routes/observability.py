"""Health probes and metrics endpoints for internal monitoring."""

import os
import hmac
from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify, request, session
from routes.auth import admin_required
from observability.alerts import (
    create_incident,
    create_silence,
    get_incident,
    list_incidents,
    notify_administrators,
    update_incident_status,
)

from observability.metrics import metrics
from observability.rules import ALERT_RULES, SLO_DEFINITIONS

observability_bp = Blueprint("observability", __name__)


@observability_bp.route("/health/live")
def liveness_probe():
    return jsonify({"status": "alive", "service": "abhihub"}), 200


@observability_bp.route("/health/ready")
def readiness_probe():
    return jsonify({
        "status": "ready",
        "service": "abhihub",
        "environment": os.getenv("FLASK_ENV", os.getenv("APP_ENV", "development")),
    }), 200


@observability_bp.route("/metrics")
def metrics_endpoint():
    configured_token = os.getenv("OBSERVABILITY_METRICS_TOKEN", "").strip()
    environment = os.getenv("FLASK_ENV", os.getenv("APP_ENV", "development")).lower()
    supplied_token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if environment in ("production", "prod") and configured_token:
        if not hmac.compare_digest(supplied_token, configured_token):
            return jsonify({"success": False, "error": "Metrics authentication required"}), 401
    return Response(
        metrics.render(),
        status=200,
        mimetype="text/plain",
        headers={"Cache-Control": "no-store"},
    )


@observability_bp.route("/api/admin/observability/rules", methods=["GET"])
@admin_required
def observability_rules():
    return jsonify({"success": True, "alerts": ALERT_RULES, "slos": SLO_DEFINITIONS})


@observability_bp.route("/health/dependencies")
def dependency_health():
    return jsonify({
        "status": "unknown",
        "service": "abhihub",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {
            "application": "healthy",
            "supabase": "not_checked",
            "notifications": "not_checked",
        },
    }), 200


@observability_bp.route("/api/admin/observability/incidents", methods=["GET"])
@admin_required
def admin_incidents():
    result = list_incidents(request.args.get("status"))
    return jsonify(result), 200 if result.get("success") else 503


@observability_bp.route("/admin/observability")
@admin_required
def observability_dashboard():
    from flask import render_template
    return render_template("admin_observability.html")


@observability_bp.route("/api/admin/observability/summary", methods=["GET"])
@admin_required
def observability_summary():
    incidents = list_incidents(limit=100)
    active = [
        item for item in incidents.get("incidents", [])
        if item.get("status") == "firing"
    ]
    return jsonify({
        "success": incidents.get("success", False),
        "active_count": len(active),
        "critical_count": sum(item.get("severity") == "critical" for item in active),
        "high_count": sum(item.get("severity") == "high" for item in active),
        "incidents": incidents.get("incidents", []),
        "alerts": ALERT_RULES,
        "slos": SLO_DEFINITIONS,
        "metrics": metrics.snapshot(),
    }), 200 if incidents.get("success") else 503


@observability_bp.route("/api/admin/observability/incidents/<incident_id>", methods=["GET"])
@admin_required
def incident_detail(incident_id):
    result = get_incident(incident_id)
    return jsonify(result), 200 if result.get("success") else 404


@observability_bp.route("/api/admin/observability/incidents", methods=["POST"])
@admin_required
def create_admin_incident():
    result = create_incident(request.get_json(silent=True) or {})
    if not result.get("success"):
        return jsonify(result), 400 if "Missing" in result.get("error", "") else 503
    if not result.get("deduplicated"):
        result["delivery"] = notify_administrators(result["incident"])
    return jsonify(result), 201


@observability_bp.route("/api/admin/observability/incidents/<incident_id>/acknowledge", methods=["POST"])
@admin_required
def acknowledge_incident(incident_id):
    user = session.get("user", {})
    result = update_incident_status(
        incident_id,
        "acknowledged",
        user.get("uid") or user.get("id", ""),
        (request.get_json(silent=True) or {}).get("note", ""),
    )
    return jsonify(result), 200 if result.get("success") else 400


@observability_bp.route("/api/admin/observability/incidents/<incident_id>/resolve", methods=["POST"])
@admin_required
def resolve_incident(incident_id):
    user = session.get("user", {})
    result = update_incident_status(
        incident_id,
        "resolved",
        user.get("uid") or user.get("id", ""),
        (request.get_json(silent=True) or {}).get("note", ""),
    )
    return jsonify(result), 200 if result.get("success") else 400


@observability_bp.route("/api/admin/observability/incidents/<incident_id>/silence", methods=["POST"])
@admin_required
def silence_incident(incident_id):
    user = session.get("user", {})
    payload = request.get_json(silent=True) or {}
    try:
        duration = int(payload.get("duration_minutes", 60))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "duration_minutes must be an integer"}), 400
    result = create_silence(
        incident_id,
        user.get("uid") or user.get("id", ""),
        duration,
        str(payload.get("reason", "")),
    )
    return jsonify(result), 201 if result.get("success") else 400
