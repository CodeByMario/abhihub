"""Health probes and metrics endpoints for internal monitoring."""

import os
import hmac
from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify, request, session
from routes.auth import admin_required
from observability.alerts import (
    create_incident,
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
