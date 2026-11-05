"""Small dependency-free metrics registry exposed in Prometheus text format."""

from collections import defaultdict
from threading import Lock
from typing import Dict, Iterable, Mapping, Tuple


def _escape(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float] = defaultdict(float)
        self._histograms: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], Dict[str, float]] = {}
        self._lock = Lock()

    @staticmethod
    def _key(labels: Mapping[str, str]) -> Tuple[Tuple[str, str], ...]:
        return tuple(sorted((str(k), str(v)) for k, v in labels.items()))

    def increment(self, name: str, labels: Mapping[str, str] = None, value: float = 1) -> None:
        key = (name, self._key(labels or {}))
        with self._lock:
            self._counters[key] += value

    def observe(self, name: str, value: float, labels: Mapping[str, str] = None) -> None:
        key = (name, self._key(labels or {}))
        with self._lock:
            histogram = self._histograms.setdefault(
                key,
                {"count": 0.0, "sum": 0.0},
            )
            histogram["count"] += 1
            histogram["sum"] += value

    def render(self) -> str:
        lines = [
            "# HELP http_requests_total Total HTTP requests handled by the application.",
            "# TYPE http_requests_total counter",
        ]
        with self._lock:
            counters = list(self._counters.items())
            histograms = list(self._histograms.items())
        for (name, labels), value in counters:
            lines.append(f"{name}{self._format_labels(labels)} {value:g}")
        for (name, labels), values in histograms:
            lines.extend([
                f"# TYPE {name} summary",
                f"{name}_count{self._format_labels(labels)} {values['count']:g}",
                f"{name}_sum{self._format_labels(labels)} {values['sum']:g}",
            ])
        return "\n".join(lines) + "\n"

    def snapshot(self) -> Dict[str, object]:
        """Return safe aggregate values for the admin dashboard and observability probes."""
        with self._lock:
            request_count = sum(
                value for (name, _labels), value in self._counters.items()
                if name == "http_requests_total"
            )
            request_duration = [
                values for (name, _labels), values in self._histograms.items()
                if name == "http_request_duration_seconds"
            ]
            cache_hits = sum(
                value for (name, _labels), value in self._counters.items()
                if name == "cache_hits_total"
            )
            cache_misses = sum(
                value for (name, _labels), value in self._counters.items()
                if name == "cache_misses_total"
            )
            supabase_queries = sum(
                value for (name, _labels), value in self._counters.items()
                if name == "supabase_queries_total"
            )
            bg_starts = sum(
                value for (name, _labels), value in self._counters.items()
                if name == "background_jobs_started_total"
            )
            bg_failures = sum(
                value for (name, _labels), value in self._counters.items()
                if name == "background_jobs_failed_total"
            )

        duration_count = sum(item["count"] for item in request_duration)
        duration_sum = sum(item["sum"] for item in request_duration)
        total_cache_reqs = cache_hits + cache_misses
        hit_rate = round((cache_hits / total_cache_reqs) * 100, 1) if total_cache_reqs else 0.0

        return {
            "request_count": int(request_count),
            "request_duration_count": int(duration_count),
            "average_request_duration_ms": round((duration_sum / duration_count) * 1000, 2) if duration_count else 0,
            "cache_hits": int(cache_hits),
            "cache_misses": int(cache_misses),
            "cache_hit_rate_pct": hit_rate,
            "supabase_queries": int(supabase_queries),
            "background_jobs_started": int(bg_starts),
            "background_jobs_failed": int(bg_failures),
        }

    @staticmethod
    def _format_labels(labels: Iterable[Tuple[str, str]]) -> str:
        if not labels:
            return ""
        rendered = ",".join(
            f'{key}="{_escape(value)}"' for key, value in labels
        )
        return "{" + rendered + "}"


metrics = MetricsRegistry()


def record_cache_event(event_type: str, level: str = "l1", key: str = "default") -> None:
    safe_key = key.split(":")[0] if ":" in key else key
    if event_type == "CACHE_HIT":
        metrics.increment("cache_hits_total", {"level": level, "key": safe_key})
    elif event_type == "CACHE_MISS":
        metrics.increment("cache_misses_total", {"level": level, "key": safe_key})
    elif event_type == "CACHE_STALE":
        metrics.increment("cache_stale_total", {"level": level, "key": safe_key})
    elif event_type == "CACHE_BYPASS":
        metrics.increment("cache_bypass_total", {"key": safe_key})
    elif event_type == "CACHE_INVALIDATION":
        metrics.increment("cache_invalidation_total", {"key": safe_key})


def record_supabase_query(table: str, action: str = "select", duration: float = 0.0) -> None:
    metrics.increment("supabase_queries_total", {"table": table, "action": action})
    if duration > 0:
        metrics.observe("supabase_query_duration_seconds", duration, {"table": table})


def record_duplicate_suppressed(endpoint: str) -> None:
    metrics.increment("duplicate_requests_suppressed_total", {"endpoint": endpoint})


def record_background_job(job_id: str, status: str = "start") -> None:
    if status == "start":
        metrics.increment("background_jobs_started_total", {"job": job_id})
    elif status == "failure":
        metrics.increment("background_jobs_failed_total", {"job": job_id})
