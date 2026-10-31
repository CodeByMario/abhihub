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

    @staticmethod
    def _format_labels(labels: Iterable[Tuple[str, str]]) -> str:
        if not labels:
            return ""
        rendered = ",".join(
            f'{key}="{_escape(value)}"' for key, value in labels
        )
        return "{" + rendered + "}"


metrics = MetricsRegistry()
