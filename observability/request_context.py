"""Request correlation, structured request logs, and HTTP metrics."""

import json
import logging
import re
import time
import uuid
from contextvars import ContextVar
from typing import Optional

from flask import Flask, g, has_request_context, request

from .metrics import metrics

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID = ContextVar("request_id", default="")
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def get_request_id() -> str:
    return _REQUEST_ID.get()


class JsonFormatter(logging.Formatter):
    """Emit stable JSON fields while preserving existing log messages."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = get_request_id()
        if request_id:
            payload["request_id"] = request_id
        trace_id = getattr(g, "trace_id", None) if has_request_context() else None
        if trace_id:
            payload["trace_id"] = trace_id
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def configure_logging() -> None:
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        root.addHandler(handler)
    root.setLevel(logging.INFO)


def _incoming_request_id() -> str:
    candidate = request.headers.get(REQUEST_ID_HEADER, "").strip()
    if _SAFE_REQUEST_ID.fullmatch(candidate):
        return candidate
    return f"req_{uuid.uuid4().hex}"


def install_request_context(app: Flask) -> None:
    configure_logging()

    @app.before_request
    def start_observability_context() -> None:
        request_id = _incoming_request_id()
        _REQUEST_ID.set(request_id)
        g.request_id = request_id
        g.trace_id = request.headers.get("traceparent", "").split("-")[1] if (
            request.headers.get("traceparent", "").count("-") >= 3
        ) else uuid.uuid4().hex
        g.request_started_at = time.perf_counter()

    @app.after_request
    def finish_observability_context(response):
        request_id: Optional[str] = getattr(g, "request_id", None)
        if request_id:
            response.headers[REQUEST_ID_HEADER] = request_id
        started = getattr(g, "request_started_at", None)
        duration = time.perf_counter() - started if started else 0
        route = request.url_rule.rule if request.url_rule else request.path
        labels = {
            "method": request.method,
            "route": route,
            "status": str(response.status_code),
        }
        metrics.increment("http_requests_total", labels)
        metrics.observe("http_request_duration_seconds", duration, labels)
        logging.getLogger("observability").info(
            "request_completed",
            extra={"request_id": request_id},
        )
        _REQUEST_ID.set("")
        return response
