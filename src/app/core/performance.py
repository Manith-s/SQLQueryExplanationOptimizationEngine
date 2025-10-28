"""
Performance monitoring and metrics for QEO.

Tracks:
- Query execution times
- Cache hit rates
- Connection pool usage
- Endpoint performance
"""

import time
from typing import Dict, Any, Optional
from collections import defaultdict
import threading


class PerformanceMetrics:
    """Thread-safe performance metrics collector."""

    def __init__(self):
        self._lock = threading.Lock()
        self._query_times: Dict[str, list] = defaultdict(list)
        self._endpoint_times: Dict[str, list] = defaultdict(list)
        self._query_counts: Dict[str, int] = defaultdict(int)
        self._error_counts: Dict[str, int] = defaultdict(int)

    def record_query_time(self, query_type: str, duration_ms: float) -> None:
        """
        Record query execution time.

        Args:
            query_type: Type of query (explain, optimize, lint, etc.)
            duration_ms: Duration in milliseconds
        """
        with self._lock:
            self._query_times[query_type].append(duration_ms)
            self._query_counts[query_type] += 1

            # Keep only last 1000 samples per query type
            if len(self._query_times[query_type]) > 1000:
                self._query_times[query_type] = self._query_times[query_type][-1000:]

    def record_endpoint_time(self, endpoint: str, duration_ms: float) -> None:
        """
        Record endpoint execution time.

        Args:
            endpoint: Endpoint path
            duration_ms: Duration in milliseconds
        """
        with self._lock:
            self._endpoint_times[endpoint].append(duration_ms)

            # Keep only last 1000 samples per endpoint
            if len(self._endpoint_times[endpoint]) > 1000:
                self._endpoint_times[endpoint] = self._endpoint_times[endpoint][-1000:]

    def record_error(self, error_type: str) -> None:
        """
        Record error occurrence.

        Args:
            error_type: Type of error
        """
        with self._lock:
            self._error_counts[error_type] += 1

    def get_query_stats(self, query_type: str) -> Dict[str, Any]:
        """Get statistics for a specific query type."""
        with self._lock:
            times = self._query_times.get(query_type, [])
            if not times:
                return {
                    "count": 0,
                    "avg_ms": 0.0,
                    "min_ms": 0.0,
                    "max_ms": 0.0,
                    "p50_ms": 0.0,
                    "p95_ms": 0.0,
                    "p99_ms": 0.0
                }

            sorted_times = sorted(times)
            count = len(sorted_times)

            return {
                "count": count,
                "avg_ms": round(sum(sorted_times) / count, 2),
                "min_ms": round(sorted_times[0], 2),
                "max_ms": round(sorted_times[-1], 2),
                "p50_ms": round(sorted_times[int(count * 0.50)], 2),
                "p95_ms": round(sorted_times[int(count * 0.95)], 2),
                "p99_ms": round(sorted_times[int(count * 0.99)], 2)
            }

    def get_endpoint_stats(self, endpoint: str) -> Dict[str, Any]:
        """Get statistics for a specific endpoint."""
        with self._lock:
            times = self._endpoint_times.get(endpoint, [])
            if not times:
                return {
                    "count": 0,
                    "avg_ms": 0.0,
                    "min_ms": 0.0,
                    "max_ms": 0.0,
                    "p95_ms": 0.0
                }

            sorted_times = sorted(times)
            count = len(sorted_times)

            return {
                "count": count,
                "avg_ms": round(sum(sorted_times) / count, 2),
                "min_ms": round(sorted_times[0], 2),
                "max_ms": round(sorted_times[-1], 2),
                "p95_ms": round(sorted_times[int(count * 0.95)], 2)
            }

    def get_all_stats(self) -> Dict[str, Any]:
        """Get all performance statistics."""
        with self._lock:
            query_stats = {
                qt: self.get_query_stats(qt)
                for qt in self._query_times.keys()
            }

            endpoint_stats = {
                ep: self.get_endpoint_stats(ep)
                for ep in self._endpoint_times.keys()
            }

            return {
                "queries": query_stats,
                "endpoints": endpoint_stats,
                "errors": dict(self._error_counts),
                "total_queries": sum(self._query_counts.values()),
                "total_errors": sum(self._error_counts.values())
            }

    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self._query_times.clear()
            self._endpoint_times.clear()
            self._query_counts.clear()
            self._error_counts.clear()


# Global metrics instance
_metrics = PerformanceMetrics()


class Timer:
    """Context manager for timing operations."""

    def __init__(self, category: str, name: str):
        """
        Initialize timer.

        Args:
            category: Category (query or endpoint)
            name: Name of operation
        """
        self.category = category
        self.name = name
        self.start_time: Optional[float] = None
        self.duration_ms: Optional[float] = None

    def __enter__(self):
        """Start timer."""
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop timer and record metrics."""
        if self.start_time is not None:
            self.duration_ms = (time.time() - self.start_time) * 1000

            if self.category == "query":
                _metrics.record_query_time(self.name, self.duration_ms)
            elif self.category == "endpoint":
                _metrics.record_endpoint_time(self.name, self.duration_ms)

        # Record error if exception occurred
        if exc_type is not None:
            _metrics.record_error(str(exc_type.__name__))

        # Don't suppress exceptions
        return False


def get_performance_metrics() -> Dict[str, Any]:
    """Get current performance metrics."""
    return _metrics.get_all_stats()


def reset_performance_metrics() -> None:
    """Reset performance metrics."""
    _metrics.reset()


def time_query(query_type: str):
    """
    Decorator to time query operations.

    Args:
        query_type: Type of query (explain, optimize, etc.)
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            with Timer("query", query_type):
                return func(*args, **kwargs)
        return wrapper
    return decorator


def time_endpoint(endpoint_path: str):
    """
    Decorator to time endpoint operations.

    Args:
        endpoint_path: Endpoint path
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            with Timer("endpoint", endpoint_path):
                return func(*args, **kwargs)
        return wrapper
    return decorator
