# Observability foundation

The application now exposes a dependency-free observability foundation:

- `X-Request-ID` is accepted, validated, generated when absent, and returned on every response.
- Request completion logs include the correlation ID and route timing.
- `GET /health/live` is a process liveness probe.
- `GET /health/ready` is a readiness probe.
- `GET /health/dependencies` reports dependency-check placeholders without secrets.
- `GET /metrics` exposes process-local metrics in Prometheus text format.
- `GET /api/admin/observability/rules` exposes the configured alert and SLO definitions to admins.

In production, set `OBSERVABILITY_METRICS_TOKEN` and send it as a bearer token when
scraping `/metrics`. If the token is not configured, the endpoint remains compatible
with existing internal deployments.

The metrics registry is intentionally process-local for this first phase. With multiple
Gunicorn workers, the next phase should add a Prometheus client multiprocess backend or
an external metrics collector before using these values for SLO decisions.

## Validation

Run:

```text
python -m pytest tests/test_observability.py tests/test_production_readiness.py -q
```
