"""
Query Performance Profiler Module

Tracks query execution history, detects performance degradation,
and provides statistical analysis of query performance over time.
"""

import hashlib
import json
import sqlite3
import statistics
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings


class QueryProfiler:
    """
    Manages query performance profiling with SQLite persistence.
    Tracks execution history and provides statistical analysis.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the profiler with SQLite database.

        Args:
            db_path: Path to SQLite database file. Defaults to profiler.db
        """
        if db_path is None:
            db_path = str(Path.cwd() / "profiler.db")
        self.db_path = db_path
        self._init_db()

        # In-memory sliding windows for real-time analysis (per query hash)
        self._windows: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=settings.PROFILER_WINDOW_SIZE)
        )

        # Load recent data into memory
        self._load_recent_data()

    def _init_db(self):
        """Initialize SQLite database schema."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS query_executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_hash TEXT NOT NULL,
                    query_text TEXT NOT NULL,
                    execution_time_ms REAL NOT NULL,
                    total_cost REAL,
                    planning_time_ms REAL,
                    execution_rows INTEGER,
                    buffer_hits INTEGER,
                    buffer_misses INTEGER,
                    cache_hit_rate REAL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_query_hash
                ON query_executions(query_hash)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON query_executions(timestamp)
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS performance_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_hash TEXT NOT NULL,
                    alert_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    metrics TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS optimization_recommendations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_hash TEXT NOT NULL,
                    recommendation_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    priority INTEGER,
                    metrics TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()

    @contextmanager
    def _get_connection(self):
        """Context manager for SQLite connections."""
        conn = sqlite3.connect(
            self.db_path,
            timeout=30.0,
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _compute_query_hash(self, query: str) -> str:
        """
        Generate a consistent hash for a query.

        Args:
            query: SQL query text

        Returns:
            SHA256 hash of normalized query
        """
        normalized = " ".join(query.lower().split())
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def _load_recent_data(self, hours: int = 24):
        """
        Load recent execution data into memory windows.

        Args:
            hours: Number of hours of recent data to load
        """
        cutoff = datetime.now() - timedelta(hours=hours)

        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT query_hash, execution_time_ms, total_cost,
                       cache_hit_rate, timestamp
                FROM query_executions
                WHERE timestamp > ?
                ORDER BY timestamp ASC
            """, (cutoff.isoformat(),)).fetchall()

            for row in rows:
                entry = {
                    "execution_time_ms": row["execution_time_ms"],
                    "total_cost": row["total_cost"],
                    "cache_hit_rate": row["cache_hit_rate"],
                    "timestamp": row["timestamp"]
                }
                self._windows[row["query_hash"]].append(entry)

    def record_execution(
        self,
        query: str,
        execution_time_ms: float,
        total_cost: Optional[float] = None,
        planning_time_ms: Optional[float] = None,
        execution_rows: Optional[int] = None,
        buffer_hits: Optional[int] = None,
        buffer_misses: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Record a query execution with performance metrics.

        Args:
            query: SQL query text
            execution_time_ms: Execution time in milliseconds
            total_cost: Query plan total cost
            planning_time_ms: Planning time in milliseconds
            execution_rows: Number of rows returned
            buffer_hits: Number of buffer hits
            buffer_misses: Number of buffer misses
            metadata: Additional metadata dictionary

        Returns:
            Query hash
        """
        query_hash = self._compute_query_hash(query)

        # Calculate cache hit rate
        cache_hit_rate = None
        if buffer_hits is not None and buffer_misses is not None:
            total_buffer = buffer_hits + buffer_misses
            if total_buffer > 0:
                cache_hit_rate = float(f"{(buffer_hits / total_buffer * 100):.3f}")

        # Store in database
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO query_executions (
                    query_hash, query_text, execution_time_ms, total_cost,
                    planning_time_ms, execution_rows, buffer_hits, buffer_misses,
                    cache_hit_rate, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                query_hash,
                query,
                execution_time_ms,
                total_cost,
                planning_time_ms,
                execution_rows,
                buffer_hits,
                buffer_misses,
                cache_hit_rate,
                json.dumps(metadata) if metadata else None
            ))
            conn.commit()

        # Add to sliding window
        entry = {
            "execution_time_ms": execution_time_ms,
            "total_cost": total_cost,
            "cache_hit_rate": cache_hit_rate,
            "timestamp": datetime.now().isoformat()
        }
        self._windows[query_hash].append(entry)

        # Check for performance degradation
        self._check_degradation(query_hash, query)

        return query_hash

    def _check_degradation(self, query_hash: str, query: str):
        """
        Check for performance degradation using sliding window analysis.

        Args:
            query_hash: Query hash identifier
            query: Original query text
        """
        window = self._windows[query_hash]

        if len(window) < settings.PROFILER_MIN_SAMPLES:
            return  # Not enough data

        # Split window into historical and recent
        split_point = len(window) // 2
        historical = list(window)[:split_point]
        recent = list(window)[split_point:]

        # Analyze execution time degradation
        hist_times = [e["execution_time_ms"] for e in historical]
        recent_times = [e["execution_time_ms"] for e in recent]

        hist_mean = statistics.mean(hist_times)
        recent_mean = statistics.mean(recent_times)

        # Check for significant degradation (threshold-based)
        degradation_pct = ((recent_mean - hist_mean) / hist_mean) * 100

        if degradation_pct > settings.PROFILER_DEGRADATION_THRESHOLD_PCT:
            self._create_alert(
                query_hash=query_hash,
                alert_type="performance_degradation",
                severity="warning",
                message=f"Query performance degraded by {degradation_pct:.1f}%",
                metrics={
                    "historical_mean_ms": float(f"{hist_mean:.3f}"),
                    "recent_mean_ms": float(f"{recent_mean:.3f}"),
                    "degradation_pct": float(f"{degradation_pct:.3f}")
                }
            )

    def _create_alert(
        self,
        query_hash: str,
        alert_type: str,
        severity: str,
        message: str,
        metrics: Optional[Dict[str, Any]] = None
    ):
        """
        Create a performance alert.

        Args:
            query_hash: Query hash identifier
            alert_type: Type of alert
            severity: Alert severity (info, warning, error)
            message: Alert message
            metrics: Associated metrics
        """
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO performance_alerts (
                    query_hash, alert_type, severity, message, metrics
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                query_hash,
                alert_type,
                severity,
                message,
                json.dumps(metrics) if metrics else None
            ))
            conn.commit()

    def get_query_statistics(
        self,
        query: Optional[str] = None,
        query_hash: Optional[str] = None,
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get statistical analysis for a query.

        Args:
            query: SQL query text (optional if query_hash provided)
            query_hash: Query hash (optional if query provided)
            hours: Number of hours to analyze

        Returns:
            Dictionary with statistical metrics
        """
        if query_hash is None and query is None:
            raise ValueError("Either query or query_hash must be provided")

        if query_hash is None:
            query_hash = self._compute_query_hash(query)

        cutoff = datetime.now() - timedelta(hours=hours)

        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT execution_time_ms, total_cost, cache_hit_rate,
                       buffer_hits, buffer_misses, execution_rows, timestamp
                FROM query_executions
                WHERE query_hash = ? AND timestamp > ?
                ORDER BY timestamp ASC
            """, (query_hash, cutoff.isoformat())).fetchall()

        if not rows:
            return {
                "query_hash": query_hash,
                "sample_count": 0,
                "message": "No execution history found"
            }

        # Extract metrics
        exec_times = [r["execution_time_ms"] for r in rows]
        costs = [r["total_cost"] for r in rows if r["total_cost"] is not None]
        cache_rates = [r["cache_hit_rate"] for r in rows if r["cache_hit_rate"] is not None]

        # Calculate statistics
        stats = {
            "query_hash": query_hash,
            "sample_count": len(rows),
            "time_window_hours": hours,
            "execution_time": self._calculate_stats(exec_times),
            "first_seen": rows[0]["timestamp"],
            "last_seen": rows[-1]["timestamp"]
        }

        if costs:
            stats["total_cost"] = self._calculate_stats(costs)

        if cache_rates:
            stats["cache_hit_rate"] = self._calculate_stats(cache_rates)

        # Trend analysis
        stats["trend"] = self._analyze_trend(exec_times)

        # Recent alerts
        stats["recent_alerts"] = self._get_recent_alerts(query_hash, hours=hours)

        return stats

    def _calculate_stats(self, values: List[float]) -> Dict[str, float]:
        """
        Calculate statistical metrics for a list of values.

        Args:
            values: List of numeric values

        Returns:
            Dictionary with mean, median, std dev, and percentiles
        """
        if not values:
            return {}

        sorted_values = sorted(values)

        result = {
            "mean": float(f"{statistics.mean(values):.3f}"),
            "median": float(f"{statistics.median(values):.3f}"),
            "min": float(f"{min(values):.3f}"),
            "max": float(f"{max(values):.3f}"),
            "p50": float(f"{sorted_values[len(sorted_values) // 2]:.3f}"),
            "p95": float(f"{sorted_values[int(len(sorted_values) * 0.95)]:.3f}"),
            "p99": float(f"{sorted_values[int(len(sorted_values) * 0.99)]:.3f}")
        }

        if len(values) > 1:
            result["std_dev"] = float(f"{statistics.stdev(values):.3f}")

        return result

    def _analyze_trend(self, values: List[float]) -> Dict[str, Any]:
        """
        Analyze trend in values over time.

        Args:
            values: List of values in chronological order

        Returns:
            Dictionary with trend analysis
        """
        if len(values) < 2:
            return {"direction": "unknown"}

        # Simple linear trend: compare first and second half
        mid = len(values) // 2
        first_half = values[:mid]
        second_half = values[mid:]

        first_mean = statistics.mean(first_half)
        second_mean = statistics.mean(second_half)

        change_pct = ((second_mean - first_mean) / first_mean) * 100

        if abs(change_pct) < 5:
            direction = "stable"
        elif change_pct > 0:
            direction = "degrading"
        else:
            direction = "improving"

        return {
            "direction": direction,
            "change_pct": float(f"{change_pct:.3f}"),
            "first_half_mean": float(f"{first_mean:.3f}"),
            "second_half_mean": float(f"{second_mean:.3f}")
        }

    def _get_recent_alerts(self, query_hash: str, hours: int = 24) -> List[Dict[str, Any]]:
        """
        Get recent alerts for a query.

        Args:
            query_hash: Query hash identifier
            hours: Number of hours to look back

        Returns:
            List of alert dictionaries
        """
        cutoff = datetime.now() - timedelta(hours=hours)

        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT alert_type, severity, message, metrics, timestamp
                FROM performance_alerts
                WHERE query_hash = ? AND timestamp > ?
                ORDER BY timestamp DESC
                LIMIT 10
            """, (query_hash, cutoff.isoformat())).fetchall()

        return [
            {
                "alert_type": r["alert_type"],
                "severity": r["severity"],
                "message": r["message"],
                "metrics": json.loads(r["metrics"]) if r["metrics"] else None,
                "timestamp": r["timestamp"]
            }
            for r in rows
        ]

    def profile_query_execution(
        self,
        query: str,
        iterations: int = 10,
        execution_func: callable = None
    ) -> Dict[str, Any]:
        """
        Profile a query by running it multiple times and collecting metrics.

        Args:
            query: SQL query to profile
            iterations: Number of times to execute the query
            execution_func: Function that executes the query and returns metrics

        Returns:
            Comprehensive profiling report
        """
        query_hash = self._compute_query_hash(query)
        results = []

        for i in range(iterations):
            start_time = time.time()

            try:
                if execution_func:
                    metrics = execution_func(query)
                else:
                    metrics = {}

                exec_time_ms = (time.time() - start_time) * 1000

                # Record execution
                self.record_execution(
                    query=query,
                    execution_time_ms=exec_time_ms,
                    total_cost=metrics.get("total_cost"),
                    planning_time_ms=metrics.get("planning_time_ms"),
                    execution_rows=metrics.get("execution_rows"),
                    buffer_hits=metrics.get("buffer_hits"),
                    buffer_misses=metrics.get("buffer_misses"),
                    metadata={"iteration": i + 1, "profiling_session": True}
                )

                results.append({
                    "iteration": i + 1,
                    "execution_time_ms": float(f"{exec_time_ms:.3f}"),
                    "metrics": metrics
                })

            except Exception as e:
                results.append({
                    "iteration": i + 1,
                    "error": str(e)
                })

        # Generate profile report
        successful_runs = [r for r in results if "error" not in r]

        if not successful_runs:
            return {
                "query_hash": query_hash,
                "status": "failed",
                "error": "All iterations failed",
                "results": results
            }

        exec_times = [r["execution_time_ms"] for r in successful_runs]

        report = {
            "query_hash": query_hash,
            "query": query,
            "status": "success",
            "iterations_requested": iterations,
            "iterations_successful": len(successful_runs),
            "execution_time_distribution": self._calculate_stats(exec_times),
            "results": results
        }

        # Add cost analysis if available
        costs = [r["metrics"].get("total_cost") for r in successful_runs if r["metrics"].get("total_cost")]
        if costs:
            report["cost_analysis"] = self._calculate_stats(costs)

        # Add historical comparison
        historical_stats = self.get_query_statistics(query_hash=query_hash, hours=168)  # 1 week
        if historical_stats.get("sample_count", 0) > 0:
            report["historical_comparison"] = historical_stats

        return report

    def get_all_query_summaries(self, hours: int = 24, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get summaries for all tracked queries.

        Args:
            hours: Number of hours to analyze
            limit: Maximum number of queries to return

        Returns:
            List of query summary dictionaries
        """
        cutoff = datetime.now() - timedelta(hours=hours)

        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT query_hash, query_text,
                       COUNT(*) as execution_count,
                       AVG(execution_time_ms) as avg_time,
                       MAX(execution_time_ms) as max_time,
                       MIN(execution_time_ms) as min_time
                FROM query_executions
                WHERE timestamp > ?
                GROUP BY query_hash
                ORDER BY execution_count DESC
                LIMIT ?
            """, (cutoff.isoformat(), limit)).fetchall()

        summaries = []
        for row in rows:
            summaries.append({
                "query_hash": row["query_hash"],
                "query_text": row["query_text"][:200] + "..." if len(row["query_text"]) > 200 else row["query_text"],
                "execution_count": row["execution_count"],
                "avg_time_ms": float(f"{row['avg_time']:.3f}"),
                "max_time_ms": float(f"{row['max_time']:.3f}"),
                "min_time_ms": float(f"{row['min_time']:.3f}")
            })

        return summaries

    def cleanup_old_data(self, days: int = 30) -> int:
        """
        Clean up old profiling data.

        Args:
            days: Number of days of data to keep

        Returns:
            Number of records deleted
        """
        cutoff = datetime.now() - timedelta(days=days)

        with self._get_connection() as conn:
            cursor = conn.execute("""
                DELETE FROM query_executions
                WHERE timestamp < ?
            """, (cutoff.isoformat(),))

            deleted = cursor.rowcount

            conn.execute("""
                DELETE FROM performance_alerts
                WHERE timestamp < ?
            """, (cutoff.isoformat(),))

            conn.commit()

        return deleted


# Global profiler instance
_profiler: Optional[QueryProfiler] = None


def get_profiler() -> QueryProfiler:
    """Get or create the global profiler instance."""
    global _profiler
    if _profiler is None:
        _profiler = QueryProfiler()
    return _profiler
