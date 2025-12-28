"""
Cache management API endpoints.

Provides endpoints for:
- Cache statistics and monitoring
- Cache warming and prefetching
- Manual cache invalidation
- Configuration management
- Effectiveness reporting
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.cache_analytics import (
    QueryCacheability,
    get_cache_analytics,
)
from app.core.cache_invalidator import get_cache_invalidator
from app.core.cache_manager import get_cache_manager
from app.core.prefetch_engine import get_prefetch_engine

router = APIRouter(prefix="/api/v1/cache")


# Request/Response Models

class CacheStatsResponse(BaseModel):
    """Cache statistics response."""
    cache_stats: Dict[str, Any]
    prefetch_stats: Dict[str, Any]
    invalidation_stats: Dict[str, Any]
    memory_stats: Dict[str, Any]


class WarmCacheRequest(BaseModel):
    """Request to warm cache."""
    queries: List[str] = Field(..., description="SQL queries to execute and cache")
    parallel: bool = Field(default=True, description="Execute in parallel")


class WarmCacheResponse(BaseModel):
    """Cache warming response."""
    total_queries: int
    successful: int
    failed: int
    total_time_ms: float
    avg_time_per_query_ms: float


class InvalidateCacheRequest(BaseModel):
    """Request to invalidate cache."""
    sql: Optional[str] = Field(None, description="Specific SQL query to invalidate")
    table: Optional[str] = Field(None, description="Invalidate all queries using this table")
    pattern: Optional[str] = Field(None, description="Pattern to match for invalidation")
    clear_all: bool = Field(default=False, description="Clear entire cache")


class InvalidateCacheResponse(BaseModel):
    """Cache invalidation response."""
    entries_invalidated: int
    message: str


class CacheConfigResponse(BaseModel):
    """Cache configuration response."""
    memory_size_mb: int
    disk_cache_enabled: bool
    disk_cache_dir: Optional[str]
    default_ttl_seconds: int
    compression_enabled: bool
    encryption_enabled: bool
    prefetch_enabled: bool
    prefetch_threshold: float
    max_prefetch_cost_ms: float


class UpdateCacheConfigRequest(BaseModel):
    """Request to update cache configuration."""
    memory_size_mb: Optional[int] = Field(None, ge=10, le=10240)
    default_ttl_seconds: Optional[int] = Field(None, ge=60, le=86400)
    prefetch_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    max_prefetch_cost_ms: Optional[float] = Field(None, ge=100, le=10000)


class UpdateCacheConfigResponse(BaseModel):
    """Cache configuration update response."""
    success: bool
    message: str
    updated_config: CacheConfigResponse


class QueryMetricsResponse(BaseModel):
    """Query performance metrics response."""
    fingerprint: str
    sql: str
    total_executions: int
    cache_hits: int
    cache_misses: int
    cache_hit_rate: float
    avg_execution_time_ms: float
    min_execution_time_ms: float
    max_execution_time_ms: float
    avg_result_size_bytes: int
    time_saved_by_cache_ms: float
    cacheability_score: float
    cacheability: str
    last_executed: Optional[datetime]


class TuningRecommendationResponse(BaseModel):
    """Cache tuning recommendation."""
    priority: str
    category: str
    title: str
    description: str
    impact: str
    action: str
    estimated_improvement: str


class EffectivenessReportResponse(BaseModel):
    """Cache effectiveness report."""
    report_time: datetime
    time_period_hours: float
    total_queries: int
    unique_queries: int
    overall_hit_rate: float
    overall_miss_rate: float
    total_time_saved_ms: float
    memory_utilization: float
    top_cached_queries: List[QueryMetricsResponse]
    cache_hostile_queries: List[QueryMetricsResponse]
    recommendations: List[TuningRecommendationResponse]


class PrefetchCandidatesResponse(BaseModel):
    """Prefetch candidates response."""
    candidates: List[Dict[str, Any]]
    total_candidates: int


class SetupTriggersRequest(BaseModel):
    """Request to setup cache invalidation triggers."""
    tables: List[str] = Field(..., description="Table names to monitor")


class SetupTriggersResponse(BaseModel):
    """Trigger setup response."""
    results: Dict[str, str]
    successful: int
    failed: int


# API Endpoints

@router.get("/stats", response_model=CacheStatsResponse)
async def get_cache_stats():
    """
    Get comprehensive cache statistics.

    Returns cache statistics including:
    - Hit/miss rates
    - Memory utilization
    - Prefetch statistics
    - Invalidation statistics
    """
    cache_manager = get_cache_manager()
    prefetch_engine = get_prefetch_engine()
    cache_invalidator = get_cache_invalidator()

    cache_stats = cache_manager.get_statistics()
    prefetch_stats = prefetch_engine.get_statistics()
    invalidation_stats = cache_invalidator.get_statistics()
    memory_stats = cache_manager.memory_cache.get_stats()

    return CacheStatsResponse(
        cache_stats=cache_stats.__dict__,
        prefetch_stats=prefetch_stats,
        invalidation_stats=invalidation_stats,
        memory_stats=memory_stats
    )


@router.post("/warm", response_model=WarmCacheResponse)
async def warm_cache(request: WarmCacheRequest, background_tasks: BackgroundTasks):
    """
    Warm cache with specified queries.

    Executes provided queries and caches their results for faster future access.

    Args:
        request: List of SQL queries to warm cache with
        background_tasks: FastAPI background tasks

    Returns:
        Warming statistics including success/failure counts and timing
    """
    if not request.queries:
        raise HTTPException(status_code=400, detail="No queries provided")

    prefetch_engine = get_prefetch_engine()

    # Execute warming in background if requested
    result = prefetch_engine.warm_cache(
        queries=request.queries,
        parallel=request.parallel
    )

    return WarmCacheResponse(**result)


@router.delete("/invalidate", response_model=InvalidateCacheResponse)
async def invalidate_cache(request: InvalidateCacheRequest):
    """
    Manually invalidate cache entries.

    Supports invalidation by:
    - Specific SQL query
    - Table name (all queries using that table)
    - Pattern matching
    - Clear all

    Args:
        request: Invalidation criteria

    Returns:
        Number of entries invalidated
    """
    cache_manager = get_cache_manager()
    entries_invalidated = 0

    if request.clear_all:
        cache_manager.clear()
        message = "All cache entries cleared"
        entries_invalidated = -1  # Unknown count

    elif request.sql:
        entries_invalidated = cache_manager.invalidate(sql=request.sql)
        message = "Invalidated cache for specific query"

    elif request.table:
        entries_invalidated = cache_manager.invalidate(table=request.table)
        message = f"Invalidated all queries using table '{request.table}'"

    elif request.pattern:
        entries_invalidated = cache_manager.invalidate(pattern=request.pattern)
        message = f"Invalidated entries matching pattern '{request.pattern}'"

    else:
        raise HTTPException(
            status_code=400,
            detail="Must provide sql, table, pattern, or clear_all"
        )

    return InvalidateCacheResponse(
        entries_invalidated=entries_invalidated,
        message=message
    )


@router.get("/config", response_model=CacheConfigResponse)
async def get_cache_config():
    """
    Get current cache configuration.

    Returns all configurable cache settings.
    """
    cache_manager = get_cache_manager()
    prefetch_engine = get_prefetch_engine()

    return CacheConfigResponse(
        memory_size_mb=cache_manager.memory_cache.max_size_bytes // (1024 * 1024),
        disk_cache_enabled=cache_manager.disk_cache_dir is not None,
        disk_cache_dir=str(cache_manager.disk_cache_dir) if cache_manager.disk_cache_dir else None,
        default_ttl_seconds=cache_manager.default_ttl_seconds,
        compression_enabled=cache_manager.enable_compression,
        encryption_enabled=cache_manager.enable_encryption,
        prefetch_enabled=prefetch_engine.enable_speculative,
        prefetch_threshold=prefetch_engine.prefetch_threshold,
        max_prefetch_cost_ms=prefetch_engine.max_prefetch_cost_ms
    )


@router.put("/config", response_model=UpdateCacheConfigResponse)
async def update_cache_config(request: UpdateCacheConfigRequest):
    """
    Update cache configuration dynamically.

    Allows runtime modification of cache settings without restart.

    Args:
        request: Configuration updates

    Returns:
        Success status and updated configuration
    """
    cache_manager = get_cache_manager()
    prefetch_engine = get_prefetch_engine()

    updated = []

    if request.memory_size_mb is not None:
        new_size_bytes = request.memory_size_mb * 1024 * 1024
        cache_manager.memory_cache.max_size_bytes = new_size_bytes
        updated.append(f"memory_size_mb={request.memory_size_mb}")

    if request.default_ttl_seconds is not None:
        cache_manager.default_ttl_seconds = request.default_ttl_seconds
        updated.append(f"default_ttl_seconds={request.default_ttl_seconds}")

    if request.prefetch_threshold is not None:
        prefetch_engine.prefetch_threshold = request.prefetch_threshold
        updated.append(f"prefetch_threshold={request.prefetch_threshold}")

    if request.max_prefetch_cost_ms is not None:
        prefetch_engine.max_prefetch_cost_ms = request.max_prefetch_cost_ms
        updated.append(f"max_prefetch_cost_ms={request.max_prefetch_cost_ms}")

    if not updated:
        raise HTTPException(status_code=400, detail="No configuration updates provided")

    # Get updated config
    updated_config = CacheConfigResponse(
        memory_size_mb=cache_manager.memory_cache.max_size_bytes // (1024 * 1024),
        disk_cache_enabled=cache_manager.disk_cache_dir is not None,
        disk_cache_dir=str(cache_manager.disk_cache_dir) if cache_manager.disk_cache_dir else None,
        default_ttl_seconds=cache_manager.default_ttl_seconds,
        compression_enabled=cache_manager.enable_compression,
        encryption_enabled=cache_manager.enable_encryption,
        prefetch_enabled=prefetch_engine.enable_speculative,
        prefetch_threshold=prefetch_engine.prefetch_threshold,
        max_prefetch_cost_ms=prefetch_engine.max_prefetch_cost_ms
    )

    return UpdateCacheConfigResponse(
        success=True,
        message=f"Updated: {', '.join(updated)}",
        updated_config=updated_config
    )


@router.get("/effectiveness", response_model=EffectivenessReportResponse)
async def get_effectiveness_report(
    time_period_hours: float = Query(default=24.0, ge=1.0, le=168.0, description="Time period to analyze"),
    top_k: int = Query(default=10, ge=1, le=50, description="Number of top queries to include")
):
    """
    Generate cache effectiveness report.

    Analyzes cache performance over specified time period and provides
    comprehensive metrics and recommendations.

    Args:
        time_period_hours: Time period to analyze in hours
        top_k: Number of top/bottom queries to include

    Returns:
        Comprehensive effectiveness report
    """
    analytics = get_cache_analytics()

    report = analytics.generate_effectiveness_report(
        time_period_hours=time_period_hours,
        top_k=top_k
    )

    # Convert to response model
    def metrics_to_response(m):
        return QueryMetricsResponse(
            fingerprint=m.fingerprint,
            sql=m.sql,
            total_executions=m.total_executions,
            cache_hits=m.cache_hits,
            cache_misses=m.cache_misses,
            cache_hit_rate=m.cache_hit_rate,
            avg_execution_time_ms=m.avg_execution_time_ms,
            min_execution_time_ms=m.min_execution_time_ms,
            max_execution_time_ms=m.max_execution_time_ms,
            avg_result_size_bytes=m.avg_result_size_bytes,
            time_saved_by_cache_ms=m.time_saved_by_cache_ms,
            cacheability_score=m.cacheability_score,
            cacheability=m.cacheability.value,
            last_executed=m.last_executed
        )

    def rec_to_response(r):
        return TuningRecommendationResponse(
            priority=r.priority.value,
            category=r.category,
            title=r.title,
            description=r.description,
            impact=r.impact,
            action=r.action,
            estimated_improvement=r.estimated_improvement
        )

    return EffectivenessReportResponse(
        report_time=report.report_time,
        time_period_hours=report.time_period_hours,
        total_queries=report.total_queries,
        unique_queries=report.unique_queries,
        overall_hit_rate=report.overall_hit_rate,
        overall_miss_rate=report.overall_miss_rate,
        total_time_saved_ms=report.total_time_saved_ms,
        memory_utilization=report.memory_utilization,
        top_cached_queries=[metrics_to_response(m) for m in report.top_cached_queries],
        cache_hostile_queries=[metrics_to_response(m) for m in report.cache_hostile_queries],
        recommendations=[rec_to_response(r) for r in report.recommendations]
    )


@router.get("/queries/metrics")
async def get_query_metrics(
    sql: Optional[str] = Query(None, description="Specific SQL query"),
    min_executions: int = Query(default=1, ge=1, description="Minimum execution count"),
    cacheability: Optional[str] = Query(None, description="Filter by cacheability level")
):
    """
    Get performance metrics for queries.

    Args:
        sql: Optional specific SQL query to get metrics for
        min_executions: Minimum execution count filter
        cacheability: Filter by cacheability level

    Returns:
        List of query metrics
    """
    analytics = get_cache_analytics()

    # Parse cacheability filter
    cacheability_enum = None
    if cacheability:
        try:
            cacheability_enum = QueryCacheability(cacheability)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid cacheability: {cacheability}. Must be one of: highly_cacheable, moderately_cacheable, poorly_cacheable, non_cacheable"
            ) from e

    metrics = analytics.get_query_metrics(
        sql=sql,
        min_executions=min_executions,
        cacheability=cacheability_enum
    )

    return {
        "metrics": [
            QueryMetricsResponse(
                fingerprint=m.fingerprint,
                sql=m.sql,
                total_executions=m.total_executions,
                cache_hits=m.cache_hits,
                cache_misses=m.cache_misses,
                cache_hit_rate=m.cache_hit_rate,
                avg_execution_time_ms=m.avg_execution_time_ms,
                min_execution_time_ms=m.min_execution_time_ms,
                max_execution_time_ms=m.max_execution_time_ms,
                avg_result_size_bytes=m.avg_result_size_bytes,
                time_saved_by_cache_ms=m.time_saved_by_cache_ms,
                cacheability_score=m.cacheability_score,
                cacheability=m.cacheability.value,
                last_executed=m.last_executed
            )
            for m in metrics
        ],
        "total": len(metrics)
    }


@router.get("/queries/cache-friendly")
async def get_cache_friendly_queries(
    top_k: int = Query(default=10, ge=1, le=50, description="Number of queries to return")
):
    """
    Get most cache-friendly queries.

    Returns queries with highest cacheability scores.

    Args:
        top_k: Number of queries to return

    Returns:
        List of cache-friendly queries
    """
    analytics = get_cache_analytics()
    metrics = analytics.get_cache_friendly_queries(top_k=top_k)

    return {
        "queries": [
            QueryMetricsResponse(
                fingerprint=m.fingerprint,
                sql=m.sql,
                total_executions=m.total_executions,
                cache_hits=m.cache_hits,
                cache_misses=m.cache_misses,
                cache_hit_rate=m.cache_hit_rate,
                avg_execution_time_ms=m.avg_execution_time_ms,
                min_execution_time_ms=m.min_execution_time_ms,
                max_execution_time_ms=m.max_execution_time_ms,
                avg_result_size_bytes=m.avg_result_size_bytes,
                time_saved_by_cache_ms=m.time_saved_by_cache_ms,
                cacheability_score=m.cacheability_score,
                cacheability=m.cacheability.value,
                last_executed=m.last_executed
            )
            for m in metrics
        ]
    }


@router.get("/queries/cache-hostile")
async def get_cache_hostile_queries(
    top_k: int = Query(default=10, ge=1, le=50, description="Number of queries to return")
):
    """
    Get least cache-friendly queries.

    Returns frequently-executed queries with lowest cacheability scores.

    Args:
        top_k: Number of queries to return

    Returns:
        List of cache-hostile queries
    """
    analytics = get_cache_analytics()
    metrics = analytics.get_cache_hostile_queries(top_k=top_k)

    return {
        "queries": [
            QueryMetricsResponse(
                fingerprint=m.fingerprint,
                sql=m.sql,
                total_executions=m.total_executions,
                cache_hits=m.cache_hits,
                cache_misses=m.cache_misses,
                cache_hit_rate=m.cache_hit_rate,
                avg_execution_time_ms=m.avg_execution_time_ms,
                min_execution_time_ms=m.min_execution_time_ms,
                max_execution_time_ms=m.max_execution_time_ms,
                avg_result_size_bytes=m.avg_result_size_bytes,
                time_saved_by_cache_ms=m.time_saved_by_cache_ms,
                cacheability_score=m.cacheability_score,
                cacheability=m.cacheability.value,
                last_executed=m.last_executed
            )
            for m in metrics
        ]
    }


@router.get("/prefetch/candidates", response_model=PrefetchCandidatesResponse)
async def get_prefetch_candidates(
    session_id: Optional[str] = Query(None, description="Session ID for predictions"),
    user_id: Optional[str] = Query(None, description="User ID for predictions"),
    top_k: int = Query(default=5, ge=1, le=20, description="Number of candidates")
):
    """
    Get prefetch candidates based on query patterns.

    Predicts likely next queries based on Markov chain analysis.

    Args:
        session_id: Optional session identifier
        user_id: Optional user identifier
        top_k: Number of candidates to return

    Returns:
        List of prefetch candidates with probabilities
    """
    prefetch_engine = get_prefetch_engine()

    candidates = prefetch_engine.predict_next_queries(
        session_id=session_id,
        user_id=user_id,
        top_k=top_k
    )

    return PrefetchCandidatesResponse(
        candidates=[
            {
                "fingerprint": c.fingerprint,
                "sql": c.sql,
                "probability": c.probability,
                "estimated_cost_ms": c.estimated_cost_ms,
                "estimated_benefit": c.estimated_benefit,
                "priority_score": c.priority_score,
                "reason": c.reason
            }
            for c in candidates
        ],
        total_candidates=len(candidates)
    )


@router.post("/triggers/setup", response_model=SetupTriggersResponse)
async def setup_invalidation_triggers(request: SetupTriggersRequest):
    """
    Setup PostgreSQL triggers for automatic cache invalidation.

    Creates triggers that send NOTIFY messages when tables are modified.

    Args:
        request: List of tables to monitor

    Returns:
        Setup results for each table
    """
    if not request.tables:
        raise HTTPException(status_code=400, detail="No tables provided")

    cache_invalidator = get_cache_invalidator()

    results = cache_invalidator.setup_triggers(request.tables)

    successful = sum(1 for status in results.values() if status == "success")
    failed = len(results) - successful

    return SetupTriggersResponse(
        results=results,
        successful=successful,
        failed=failed
    )
