"""
Baseline CPU and AI token telemetry for Vercel Fluid serverless.
Uses time.thread_time() to measure active CPU per request without interference
from concurrent async/fluid invocations on the same instance.
"""
import time
import json
import logging
from collections import defaultdict, deque
from typing import Optional, Dict, Any

logger = logging.getLogger("telemetry.perf")

# In-memory recent samples ring-buffer for dev/benchmark reporting (per-process)
_MAX_SAMPLES = 500
_samples = defaultdict(lambda: deque(maxlen=_MAX_SAMPLES))
_ai_tokens = deque(maxlen=_MAX_SAMPLES)


def _record_sample(endpoint: str, cpu_ms: float, wall_ms: float, data: Dict[str, Any]):
    _samples[endpoint].append({
        "cpu_ms": cpu_ms,
        "wall_ms": wall_ms,
        "timestamp": time.time(),
        **data
    })
    if "prompt_tokens" in data or "completion_tokens" in data:
        _ai_tokens.append({
            "model_id": data.get("model_id"),
            "prompt_tokens": data.get("prompt_tokens", 0) or 0,
            "completion_tokens": data.get("completion_tokens", 0) or 0,
            "cost_estimate": data.get("cost_estimate", 0.0) or 0.0,
            "cpu_ms": cpu_ms,
        })


class measure_thread_cpu:
    """
    Context manager to measure active thread CPU and wall time for an endpoint.
    Usage:
        with measure_thread_cpu('/api/extract-ocr') as meta:
            # perform task
            meta['doc_id'] = doc_id
    """
    def __init__(self, endpoint: str, extra_meta: Optional[Dict[str, Any]] = None):
        self.endpoint = endpoint
        self.meta = dict(extra_meta or {})
        self.t_cpu_start = 0.0
        self.t_wall_start = 0.0

    def __enter__(self):
        self.t_cpu_start = time.thread_time()
        self.t_wall_start = time.monotonic()
        return self.meta

    def __exit__(self, exc_type, exc_val, exc_tb):
        cpu_ms = round((time.thread_time() - self.t_cpu_start) * 1000, 3)
        wall_ms = round((time.monotonic() - self.t_wall_start) * 1000, 3)
        payload = {
            "event": "perf_cpu",
            "endpoint": self.endpoint,
            "cpu_ms": cpu_ms,
            "wall_ms": wall_ms,
            **self.meta
        }
        logger.info("[PERF_CPU] %s", json.dumps(payload))
        _record_sample(self.endpoint, cpu_ms, wall_ms, self.meta)
        try:
            from methods.load_governor import record_request_cpu
            record_request_cpu(cpu_ms)
        except Exception:
            pass
        return False


def log_ai_perf(endpoint: str, cpu_ms: float, wall_ms: float,
                model_id: str, prompt_tokens: int,
                completion_tokens: int, cost_estimate: float):
    """Emit structured AI execution log with token counts and cost estimate."""
    payload = {
        "event": "perf_ai",
        "endpoint": endpoint,
        "cpu_ms": round(cpu_ms, 3),
        "wall_ms": round(wall_ms, 3),
        "model_id": model_id or "unknown",
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "cost_estimate": float(cost_estimate or 0.0)
    }
    logger.info("[PERF_AI] %s", json.dumps(payload))
    _record_sample(endpoint, cpu_ms, wall_ms, {
        "model_id": payload["model_id"],
        "prompt_tokens": payload["prompt_tokens"],
        "completion_tokens": payload["completion_tokens"],
        "cost_estimate": payload["cost_estimate"]
    })


def get_baseline_summary() -> Dict[str, Any]:
    """Compute avg and p95 CPU-ms per endpoint and average token metrics."""
    endpoints_summary = {}

    for ep, records in _samples.items():
        if not records:
            continue
        cpu_values = sorted([r["cpu_ms"] for r in records])
        n = len(cpu_values)
        avg_cpu = round(sum(cpu_values) / n, 2)
        p95_idx = min(int(n * 0.95), n - 1)
        p95_cpu = round(cpu_values[p95_idx], 2)
        wall_values = [r["wall_ms"] for r in records]
        avg_wall = round(sum(wall_values) / n, 2)

        endpoints_summary[ep] = {
            "count": n,
            "avg_cpu_ms": avg_cpu,
            "p95_cpu_ms": p95_cpu,
            "avg_wall_ms": avg_wall
        }

    ai_summary = {
        "total_calls": len(_ai_tokens),
        "avg_prompt_tokens": 0,
        "avg_completion_tokens": 0,
        "avg_cost_estimate": 0.0
    }
    if _ai_tokens:
        total = len(_ai_tokens)
        ai_summary["avg_prompt_tokens"] = round(sum(t["prompt_tokens"] for t in _ai_tokens) / total, 1)
        ai_summary["avg_completion_tokens"] = round(sum(t["completion_tokens"] for t in _ai_tokens) / total, 1)
        ai_summary["avg_cost_estimate"] = round(sum(t["cost_estimate"] for t in _ai_tokens) / total, 6)

    return {
        "endpoints": endpoints_summary,
        "ai": ai_summary
    }
