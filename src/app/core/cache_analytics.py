"""
Comprehensive cache analytics and monitoring system.

Provides:
- Cache effectiveness analysis and reporting
- Query performance tracking
- Cache tuning recommendations
- Identification of cache-friendly vs cache-hostile queries
- Performance impact measurement
"""

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from app.core.cache_invalidator import get_cache_invalidator
from app.core.cache_manager import QueryFingerprinter, get_cache_manager
from app.core.prefetch_engine import get_prefetch_engine


class QueryCacheability(Enum):
    """Query cacheability classifications."""

    HIGHLY_CACHEABLE = "highly_cacheable"
    MODERATELY_CACHEABLE = "moderately_cacheable"
    POORLY_CACHEABLE = "poorly_cacheable"
    NON_CACHEABLE = "non_cacheable"


class CacheTuningPriority(Enum):
    """Priority levels for tuning recommendations."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class QueryPerformanceMetrics:
    """Performance metrics for a specific query."""

    fingerprint: str
    sql: str
    total_executions: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    avg_execution_time_ms: float = 0.0
    min_execution_time_ms: float = float("inf")
    max_execution_time_ms: float = 0.0
    total_execution_time_ms: float = 0.0
    avg_result_size_bytes: int = 0
    total_result_size_bytes: int = 0
    last_executed: Optional[datetime] = None
    cache_hit_rate: float = 0.0
    time_saved_by_cache_ms: float = 0.0
    cacheability_score: float = 0.0
    cacheability: QueryCacheability = QueryCacheability.MODERATELY_CACHEABLE

    def update(self):
        """Update calculated fields."""
        if self.total_executions > 0:
            self.cache_hit_rate = self.cache_hits / self.total_executions
            self.avg_execution_time_ms = (
                self.total_execution_time_ms / self.total_executions
            )
            self.avg_result_size_bytes = int(
                self.total_result_size_bytes / self.total_executions
            )

        # Calculate time saved by cache (hits * avg execution time)
        self.time_saved_by_cache_ms = self.cache_hits * self.avg_execution_time_ms

        # Calculate cacheability score (0-100)
        self._calculate_cacheability()

    def _calculate_cacheability(self):
        """Calculate cacheability score based on multiple factors."""
        score = 0.0

        # Factor 1: Hit rate (0-40 points)
        score += self.cache_hit_rate * 40

        # Factor 2: Execution frequency (0-20 points)
        if self.total_executions >= 100:
            score += 20
        elif self.total_executions >= 50:
            score += 15
        elif self.total_executions >= 10:
            score += 10
        elif self.total_executions >= 5:
            score += 5

        # Factor 3: Execution time (0-20 points)
        # Expensive queries benefit more from caching
        if self.avg_execution_time_ms >= 1000:
            score += 20
        elif self.avg_execution_time_ms >= 500:
            score += 15
        elif self.avg_execution_time_ms >= 100:
            score += 10
        elif self.avg_execution_time_ms >= 50:
            score += 5

        # Factor 4: Result size (0-10 points)
        # Moderate size results are most cacheable
        size_kb = self.avg_result_size_bytes / 1024
        if 1 <= size_kb <= 100:
            score += 10
        elif 100 < size_kb <= 500:
            score += 7
        elif 500 < size_kb <= 1000:
            score += 4
        # Very large results penalize caching

        # Factor 5: Consistency (0-10 points)
        # Queries with consistent execution time are more predictable
        if self.total_executions > 1:
            time_range = self.max_execution_time_ms - self.min_execution_time_ms
            if time_range < self.avg_execution_time_ms * 0.2:
                score += 10  # Very consistent
            elif time_range < self.avg_execution_time_ms * 0.5:
                score += 6  # Moderately consistent
            elif time_range < self.avg_execution_time_ms:
                score += 3  # Somewhat consistent

        self.cacheability_score = min(100.0, score)

        # Classify cacheability
        if self.cacheability_score >= 75:
            self.cacheability = QueryCacheability.HIGHLY_CACHEABLE
        elif self.cacheability_score >= 50:
            self.cacheability = QueryCacheability.MODERATELY_CACHEABLE
        elif self.cacheability_score >= 25:
            self.cacheability = QueryCacheability.POORLY_CACHEABLE
        else:
            self.cacheability = QueryCacheability.NON_CACHEABLE


@dataclass
class CacheTuningRecommendation:
    """Recommendation for cache tuning."""

    priority: CacheTuningPriority
    category: str
    title: str
    description: str
    impact: str
    action: str
    estimated_improvement: str


@dataclass
class CacheEffectivenessReport:
    """Comprehensive cache effectiveness report."""

    report_time: datetime
    time_period_hours: float
    total_queries: int
    unique_queries: int
    overall_hit_rate: float
    overall_miss_rate: float
    total_time_saved_ms: float
    memory_utilization: float
    top_cached_queries: List[QueryPerformanceMetrics]
    cache_hostile_queries: List[QueryPerformanceMetrics]
    recommendations: List[CacheTuningRecommendation]
    cache_statistics: Dict[str, Any]
    prefetch_statistics: Dict[str, Any]
    invalidation_statistics: Dict[str, Any]


class CacheAnalytics:
    """
    Comprehensive cache analytics and monitoring.

    Tracks query performance, analyzes cache effectiveness,
    and provides tuning recommendations.
    """

    def __init__(
        self,
        cache_manager=None,
        prefetch_engine=None,
        cache_invalidator=None,
        max_metrics_history: int = 10000,
    ):
        """
        Initialize cache analytics.

        Args:
            cache_manager: Cache manager instance
            prefetch_engine: Prefetch engine instance
            cache_invalidator: Cache invalidator instance
            max_metrics_history: Maximum metrics to retain
        """
        self.cache_manager = cache_manager or get_cache_manager()
        self.prefetch_engine = prefetch_engine or get_prefetch_engine()
        self.cache_invalidator = cache_invalidator or get_cache_invalidator()

        # Query metrics tracking
        self.query_metrics: Dict[str, QueryPerformanceMetrics] = {}
        self.recent_queries: deque = deque(maxlen=max_metrics_history)

        # Time series data for trending
        self.hourly_stats: deque = deque(maxlen=24 * 7)  # 1 week of hourly stats

        # Start time for analytics
        self.start_time = datetime.utcnow()

    def record_query(
        self,
        sql: str,
        execution_time_ms: float,
        cache_hit: bool,
        result_size_bytes: int = 0,
    ):
        """
        Record a query execution for analytics.

        Args:
            sql: SQL query text
            execution_time_ms: Execution time in milliseconds
            cache_hit: Whether result came from cache
            result_size_bytes: Size of result set
        """
        fingerprint = QueryFingerprinter.generate_fingerprint(sql)

        # Get or create metrics
        if fingerprint not in self.query_metrics:
            self.query_metrics[fingerprint] = QueryPerformanceMetrics(
                fingerprint=fingerprint, sql=sql
            )

        metrics = self.query_metrics[fingerprint]

        # Update metrics
        metrics.total_executions += 1
        if cache_hit:
            metrics.cache_hits += 1
        else:
            metrics.cache_misses += 1

        metrics.total_execution_time_ms += execution_time_ms
        metrics.total_result_size_bytes += result_size_bytes
        metrics.min_execution_time_ms = min(
            metrics.min_execution_time_ms, execution_time_ms
        )
        metrics.max_execution_time_ms = max(
            metrics.max_execution_time_ms, execution_time_ms
        )
        metrics.last_executed = datetime.utcnow()

        # Update calculated fields
        metrics.update()

        # Add to recent queries
        self.recent_queries.append(
            {
                "fingerprint": fingerprint,
                "timestamp": datetime.utcnow(),
                "execution_time_ms": execution_time_ms,
                "cache_hit": cache_hit,
            }
        )

    def generate_effectiveness_report(
        self, time_period_hours: float = 24.0, top_k: int = 10
    ) -> CacheEffectivenessReport:
        """
        Generate comprehensive cache effectiveness report.

        Args:
            time_period_hours: Time period to analyze
            top_k: Number of top/bottom queries to include

        Returns:
            Effectiveness report
        """
        # Filter queries within time period
        cutoff_time = datetime.utcnow() - timedelta(hours=time_period_hours)

        recent_metrics = [
            m
            for m in self.query_metrics.values()
            if m.last_executed and m.last_executed >= cutoff_time
        ]

        # Calculate overall statistics
        total_queries = sum(m.total_executions for m in recent_metrics)
        unique_queries = len(recent_metrics)

        total_hits = sum(m.cache_hits for m in recent_metrics)
        total_misses = sum(m.cache_misses for m in recent_metrics)

        overall_hit_rate = (
            total_hits / (total_hits + total_misses)
            if (total_hits + total_misses) > 0
            else 0.0
        )
        overall_miss_rate = 1.0 - overall_hit_rate

        total_time_saved = sum(m.time_saved_by_cache_ms for m in recent_metrics)

        # Get cache statistics
        cache_stats = self.cache_manager.get_statistics()
        prefetch_stats = self.prefetch_engine.get_statistics()
        invalidation_stats = self.cache_invalidator.get_statistics()

        # Get memory utilization
        memory_stats = self.cache_manager.memory_cache.get_stats()
        memory_utilization = memory_stats.get("utilization", 0.0)

        # Identify top cached queries (highest time savings)
        top_cached = sorted(
            recent_metrics, key=lambda m: m.time_saved_by_cache_ms, reverse=True
        )[:top_k]

        # Identify cache-hostile queries (low hit rate, high frequency)
        cache_hostile = sorted(
            [m for m in recent_metrics if m.total_executions >= 5],
            key=lambda m: (m.cache_hit_rate, -m.total_executions),
        )[:top_k]

        # Generate recommendations
        recommendations = self._generate_recommendations(
            recent_metrics, cache_stats, memory_utilization
        )

        return CacheEffectivenessReport(
            report_time=datetime.utcnow(),
            time_period_hours=time_period_hours,
            total_queries=total_queries,
            unique_queries=unique_queries,
            overall_hit_rate=overall_hit_rate,
            overall_miss_rate=overall_miss_rate,
            total_time_saved_ms=total_time_saved,
            memory_utilization=memory_utilization,
            top_cached_queries=top_cached,
            cache_hostile_queries=cache_hostile,
            recommendations=recommendations,
            cache_statistics=cache_stats.__dict__,
            prefetch_statistics=prefetch_stats,
            invalidation_statistics=invalidation_stats,
        )

    def get_query_metrics(
        self,
        sql: Optional[str] = None,
        min_executions: int = 1,
        cacheability: Optional[QueryCacheability] = None,
    ) -> List[QueryPerformanceMetrics]:
        """
        Get query performance metrics with optional filtering.

        Args:
            sql: Specific SQL query (None = all queries)
            min_executions: Minimum execution count
            cacheability: Filter by cacheability level

        Returns:
            List of query metrics
        """
        metrics = list(self.query_metrics.values())

        if sql:
            fingerprint = QueryFingerprinter.generate_fingerprint(sql)
            metrics = [m for m in metrics if m.fingerprint == fingerprint]

        if min_executions > 1:
            metrics = [m for m in metrics if m.total_executions >= min_executions]

        if cacheability:
            metrics = [m for m in metrics if m.cacheability == cacheability]

        return metrics

    def get_cache_friendly_queries(
        self, top_k: int = 10
    ) -> List[QueryPerformanceMetrics]:
        """
        Get most cache-friendly queries.

        Args:
            top_k: Number of queries to return

        Returns:
            List of query metrics sorted by cacheability
        """
        return sorted(
            self.query_metrics.values(),
            key=lambda m: m.cacheability_score,
            reverse=True,
        )[:top_k]

    def get_cache_hostile_queries(
        self, top_k: int = 10
    ) -> List[QueryPerformanceMetrics]:
        """
        Get least cache-friendly queries.

        Args:
            top_k: Number of queries to return

        Returns:
            List of query metrics sorted by cacheability (ascending)
        """
        # Only consider queries that have been executed multiple times
        frequent_queries = [
            m for m in self.query_metrics.values() if m.total_executions >= 5
        ]

        return sorted(frequent_queries, key=lambda m: m.cacheability_score)[:top_k]

    def _generate_recommendations(
        self,
        metrics: List[QueryPerformanceMetrics],
        cache_stats: Any,
        memory_utilization: float,
    ) -> List[CacheTuningRecommendation]:
        """Generate cache tuning recommendations."""
        recommendations = []

        # Recommendation 1: Low overall hit rate
        if cache_stats.hit_rate < 0.5:
            recommendations.append(
                CacheTuningRecommendation(
                    priority=CacheTuningPriority.HIGH,
                    category="Performance",
                    title="Low Cache Hit Rate",
                    description=f"Current cache hit rate is {cache_stats.hit_rate:.1%}, which is below optimal.",
                    impact="High - Many queries are not benefiting from caching",
                    action="Increase cache memory size or adjust TTL settings to retain entries longer",
                    estimated_improvement=f"Could improve hit rate by {(0.7 - cache_stats.hit_rate) * 100:.0f}%",
                )
            )

        # Recommendation 2: High memory pressure
        if memory_utilization > 0.9:
            recommendations.append(
                CacheTuningRecommendation(
                    priority=CacheTuningPriority.CRITICAL,
                    category="Capacity",
                    title="High Memory Utilization",
                    description=f"Cache memory utilization is {memory_utilization:.1%}",
                    impact="Critical - Frequent evictions may be hurting performance",
                    action="Increase CACHE_MEMORY_SIZE_MB setting or enable disk cache",
                    estimated_improvement="Reduce eviction rate by 50%+",
                )
            )

        # Recommendation 3: Cache-hostile queries
        hostile = [
            m
            for m in metrics
            if m.cacheability == QueryCacheability.POORLY_CACHEABLE
            and m.total_executions >= 10
        ]
        if len(hostile) > 5:
            recommendations.append(
                CacheTuningRecommendation(
                    priority=CacheTuningPriority.MEDIUM,
                    category="Query Optimization",
                    title="Multiple Cache-Hostile Queries",
                    description=f"Found {len(hostile)} frequently-executed queries with poor cache performance",
                    impact="Medium - These queries are wasting cache resources",
                    action="Review and optimize cache-hostile queries, or exclude them from caching",
                    estimated_improvement="Free up 20-30% of cache memory",
                )
            )

        # Recommendation 4: Low prefetch success rate
        prefetch_stats = self.prefetch_engine.get_statistics()
        if (
            prefetch_stats.get("total_prefetch_attempts", 0) > 100
            and prefetch_stats.get("success_rate", 1.0) < 0.3
        ):
            recommendations.append(
                CacheTuningRecommendation(
                    priority=CacheTuningPriority.MEDIUM,
                    category="Prefetching",
                    title="Low Prefetch Success Rate",
                    description=f"Prefetch success rate is {prefetch_stats['success_rate']:.1%}",
                    impact="Medium - Wasted resources on unnecessary prefetching",
                    action="Increase prefetch_threshold setting or disable speculative execution",
                    estimated_improvement="Reduce wasted prefetch cycles by 50%",
                )
            )

        # Recommendation 5: Enable compression for large results
        large_results = [
            m for m in metrics if m.avg_result_size_bytes > 100 * 1024
        ]  # > 100KB
        if len(large_results) > 5:
            recommendations.append(
                CacheTuningRecommendation(
                    priority=CacheTuningPriority.LOW,
                    category="Optimization",
                    title="Large Result Sets",
                    description=f"Found {len(large_results)} queries with result sets > 100KB",
                    impact="Low - Could save cache memory through compression",
                    action="Ensure compression is enabled for large cache entries",
                    estimated_improvement="Save 30-50% cache memory for large results",
                )
            )

        # Sort by priority
        priority_order = {
            CacheTuningPriority.CRITICAL: 0,
            CacheTuningPriority.HIGH: 1,
            CacheTuningPriority.MEDIUM: 2,
            CacheTuningPriority.LOW: 3,
        }
        recommendations.sort(key=lambda r: priority_order[r.priority])

        return recommendations

    def get_time_series_stats(self, hours: int = 24) -> List[Dict[str, Any]]:
        """
        Get time series statistics.

        Args:
            hours: Number of hours to include

        Returns:
            List of hourly statistics
        """
        # In a real implementation, this would return actual time series data
        # For now, return a placeholder
        return list(self.hourly_stats)[-hours:]

    def reset_statistics(self):
        """Reset all analytics data."""
        self.query_metrics.clear()
        self.recent_queries.clear()
        self.hourly_stats.clear()
        self.start_time = datetime.utcnow()


# Singleton instance
_cache_analytics: Optional[CacheAnalytics] = None


def get_cache_analytics() -> CacheAnalytics:
    """Get singleton cache analytics instance."""
    global _cache_analytics

    if _cache_analytics is None:
        _cache_analytics = CacheAnalytics()

    return _cache_analytics
