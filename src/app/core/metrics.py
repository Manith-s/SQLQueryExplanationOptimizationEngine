"""Prometheus metrics plumbing (opt-in).

When METRICS_ENABLED=false, this module should not register collectors.
"""

from __future__ import annotations

import time

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

from app.core.config import settings

_registry: CollectorRegistry | None = None
_c_requests: Counter | None = None
_h_latency: Histogram | None = None
_h_db_explain: Histogram | None = None
_c_db_errors: Counter | None = None
_h_llm_latency: Histogram | None = None
_c_whatif_trials: Counter | None = None
_h_whatif_trial_seconds: Histogram | None = None
_c_whatif_filtered: Counter | None = None


def _buckets() -> list[float]:
    try:
        return [float(x) for x in (settings.METRICS_BUCKETS or "").split(",") if x]
    except Exception:
        return [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5]


def init_metrics() -> None:
    global _registry, _c_requests, _h_latency, _h_db_explain, _c_db_errors, _h_llm_latency, _c_whatif_trials, _h_whatif_trial_seconds, _c_whatif_filtered
    if not settings.METRICS_ENABLED:
        return
    if _registry is not None:
        return  # avoid duplicate collectors on reload
    _registry = CollectorRegistry()
    ns = settings.METRICS_NAMESPACE
    buckets = _buckets()
    _c_requests = Counter(
        f"{ns}_requests_total",
        "HTTP requests",
        labelnames=("route", "method", "status"),
        registry=_registry,
    )
    _h_latency = Histogram(
        f"{ns}_request_latency_seconds",
        "HTTP request latency",
        labelnames=("route", "method", "status"),
        buckets=buckets,
        registry=_registry,
    )
    _h_db_explain = Histogram(
        f"{ns}_db_explain_seconds",
        "DB EXPLAIN/ANALYZE duration",
        buckets=buckets,
        registry=_registry,
    )
    _c_db_errors = Counter(
        f"{ns}_db_errors_total",
        "DB errors count",
        registry=_registry,
    )
    _h_llm_latency = Histogram(
        f"{ns}_llm_latency_seconds",
        "LLM generation latency",
        buckets=buckets,
        registry=_registry,
    )
    _c_whatif_trials = Counter(
        f"{ns}_whatif_trials_total",
        "What-if (HypoPG) trials executed",
        registry=_registry,
    )
    _h_whatif_trial_seconds = Histogram(
        f"{ns}_whatif_trial_seconds",
        "What-if trial duration seconds",
        buckets=buckets,
        registry=_registry,
    )
    _c_whatif_filtered = Counter(
        f"{ns}_whatif_filtered_total",
        "What-if suggestions filtered below min reduction threshold",
        registry=_registry,
    )


def observe_request(route: str, method: str, status: int, dur_s: float) -> None:
    if not settings.METRICS_ENABLED or _registry is None:
        return
    # Keep labels low-cardinality: route template paths only
    r = route
    _c_requests.labels(route=r, method=method, status=str(status)).inc()
    _h_latency.labels(route=r, method=method, status=str(status)).observe(dur_s)


def time_db_explain(func):
    def wrapper(*args, **kwargs):
        if not settings.METRICS_ENABLED or _registry is None:
            return func(*args, **kwargs)
        start = time.time()
        try:
            return func(*args, **kwargs)
        except Exception:
            _c_db_errors.inc()
            raise
        finally:
            _h_db_explain.observe(max(time.time() - start, 0.0))
    return wrapper


def observe_llm_latency(seconds: float) -> None:
    if not settings.METRICS_ENABLED or _registry is None:
        return
    _h_llm_latency.observe(max(seconds, 0.0))


def observe_whatif_trial(seconds: float) -> None:
    if not settings.METRICS_ENABLED or _registry is None:
        return
    _c_whatif_trials.inc()
    _h_whatif_trial_seconds.observe(max(seconds, 0.0))


def count_whatif_filtered(n: int) -> None:
    if not settings.METRICS_ENABLED or _registry is None:
        return
    if n > 0:
        _c_whatif_filtered.inc(n)


def metrics_exposition() -> tuple[bytes, str]:
    if not settings.METRICS_ENABLED or _registry is None:
        return (b"metrics disabled", CONTENT_TYPE_LATEST)
    data = generate_latest(_registry)
    return (data, CONTENT_TYPE_LATEST)


