"""Declarative starting point for alert rules and service-level objectives."""

ALERT_RULES = (
    {
        "name": "http-5xx-rate",
        "severity": "high",
        "metric": "http_requests_total",
        "condition": "5xx_rate > 0.05",
        "for": "5m",
    },
    {
        "name": "http-p95-latency",
        "severity": "medium",
        "metric": "http_request_duration_seconds",
        "condition": "p95 > 1.0",
        "for": "10m",
    },
    {
        "name": "admin-alert-delivery-failure",
        "severity": "critical",
        "metric": "admin_alert_delivery_failures_total",
        "condition": "increase > 0",
        "for": "2m",
    },
    {
        "name": "admin-authorization-failures",
        "severity": "high",
        "metric": "admin_authorization_failures_total",
        "condition": "increase >= 10",
        "for": "5m",
    },
)

SLO_DEFINITIONS = (
    {
        "name": "api-availability",
        "target": 99.9,
        "window": "30d",
        "indicator": "successful_non_5xx_requests",
    },
    {
        "name": "api-latency",
        "target": 95.0,
        "window": "30d",
        "indicator": "requests_under_1_second",
    },
    {
        "name": "admin-alert-delivery",
        "target": 99.0,
        "window": "30d",
        "indicator": "alerts_delivered_within_60_seconds",
    },
)
