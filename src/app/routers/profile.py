"""
Query Profiler API Router

Provides endpoints for query performance profiling, real-time monitoring,
and historical analysis.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.db import run_explain
from app.core.profiler import get_profiler


router = APIRouter(prefix="/api/v1/profile", tags=["profiler"])


# Request/Response Models
class ProfileRequest(BaseModel):
    """Request model for query profiling."""
    sql: str = Field(..., min_length=1, description="SQL query to profile")
    iterations: int = Field(default=10, ge=1, le=100, description="Number of iterations")
    analyze: bool = Field(default=False, description="Run EXPLAIN ANALYZE (executes query)")
    timeout_ms: Optional[int] = Field(default=5000, ge=100, le=60000, description="Timeout per execution in ms")


class ProfileResponse(BaseModel):
    """Response model for query profiling."""
    query_hash: str
    query: str
    status: str
    iterations_requested: int
    iterations_successful: int
    execution_time_distribution: Dict[str, float]
    cost_analysis: Optional[Dict[str, float]] = None
    cache_analysis: Optional[Dict[str, float]] = None
    historical_comparison: Optional[Dict[str, Any]] = None
    anomalies_detected: List[str] = []
    results: List[Dict[str, Any]]


class QueryStatisticsRequest(BaseModel):
    """Request model for query statistics."""
    sql: Optional[str] = None
    query_hash: Optional[str] = None
    hours: int = Field(default=24, ge=1, le=168, description="Time window in hours")


class QuerySummaryResponse(BaseModel):
    """Response model for query summaries."""
    summaries: List[Dict[str, Any]]
    total_queries: int
    time_window_hours: int


class WebSocketConnectionManager:
    """Manages WebSocket connections for real-time monitoring."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accept and store a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast a message to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)


# Global WebSocket manager
ws_manager = WebSocketConnectionManager()


@router.post("", response_model=ProfileResponse)
async def profile_query(
    request: ProfileRequest,
    background_tasks: BackgroundTasks
):
    """
    Profile a query by executing it multiple times and collecting performance metrics.

    This endpoint:
    - Executes the query multiple times (configurable iterations)
    - Collects execution time, cost, and buffer statistics
    - Detects performance anomalies
    - Compares against historical data
    - Broadcasts results to WebSocket clients

    Returns comprehensive profiling data including statistical analysis.
    """
    if not settings.PROFILER_ENABLED:
        raise HTTPException(status_code=503, detail="Profiler is disabled")

    profiler = get_profiler()

    # Define execution function that collects metrics
    async def execute_query_with_metrics(query: str) -> Dict[str, Any]:
        """Execute query and collect EXPLAIN metrics."""
        try:
            plan_result = await asyncio.to_thread(
                run_explain,
                query,
                analyze=request.analyze,
                timeout_ms=request.timeout_ms
            )

            plan_json = plan_result.get("plan", {})

            # Extract metrics from EXPLAIN plan
            metrics = {
                "total_cost": plan_json.get("Total Cost"),
                "planning_time_ms": plan_result.get("Planning Time"),
                "execution_rows": plan_json.get("Plan Rows"),
                "buffer_hits": plan_json.get("Shared Hit Blocks"),
                "buffer_misses": plan_json.get("Shared Read Blocks")
            }

            return metrics

        except Exception as e:
            return {"error": str(e)}

    # Run profiling
    try:
        results = []
        for i in range(request.iterations):
            start_time = time.time()

            try:
                metrics = await execute_query_with_metrics(request.sql)
                exec_time_ms = (time.time() - start_time) * 1000

                # Record in profiler
                profiler.record_execution(
                    query=request.sql,
                    execution_time_ms=exec_time_ms,
                    total_cost=metrics.get("total_cost"),
                    planning_time_ms=metrics.get("planning_time_ms"),
                    execution_rows=metrics.get("execution_rows"),
                    buffer_hits=metrics.get("buffer_hits"),
                    buffer_misses=metrics.get("buffer_misses"),
                    metadata={"iteration": i + 1, "api_profile": True}
                )

                results.append({
                    "iteration": i + 1,
                    "execution_time_ms": float(f"{exec_time_ms:.3f}"),
                    "metrics": metrics
                })

                # Broadcast to WebSocket clients
                await ws_manager.broadcast({
                    "type": "profile_iteration",
                    "iteration": i + 1,
                    "total_iterations": request.iterations,
                    "execution_time_ms": float(f"{exec_time_ms:.3f}"),
                    "metrics": metrics
                })

            except Exception as e:
                results.append({
                    "iteration": i + 1,
                    "error": str(e)
                })

        # Generate analysis
        successful_runs = [r for r in results if "error" not in r]

        if not successful_runs:
            raise HTTPException(
                status_code=500,
                detail="All profiling iterations failed"
            )

        exec_times = [r["execution_time_ms"] for r in successful_runs]
        query_hash = profiler._compute_query_hash(request.sql)

        # Calculate statistics
        exec_stats = profiler._calculate_stats(exec_times)

        # Cost analysis
        costs = [
            r["metrics"].get("total_cost")
            for r in successful_runs
            if r["metrics"].get("total_cost")
        ]
        cost_analysis = profiler._calculate_stats(costs) if costs else None

        # Cache analysis
        cache_rates = []
        for r in successful_runs:
            metrics = r.get("metrics", {})
            hits = metrics.get("buffer_hits")
            misses = metrics.get("buffer_misses")
            if hits is not None and misses is not None:
                total = hits + misses
                if total > 0:
                    cache_rates.append((hits / total) * 100)

        cache_analysis = profiler._calculate_stats(cache_rates) if cache_rates else None

        # Get historical comparison
        historical_stats = profiler.get_query_statistics(
            query_hash=query_hash,
            hours=168  # 1 week
        )

        # Detect anomalies
        anomalies = []
        if historical_stats.get("sample_count", 0) > 0:
            hist_mean = historical_stats.get("execution_time", {}).get("mean")
            current_mean = exec_stats.get("mean")

            if hist_mean and current_mean:
                deviation_pct = ((current_mean - hist_mean) / hist_mean) * 100
                if abs(deviation_pct) > 25:
                    direction = "slower" if deviation_pct > 0 else "faster"
                    anomalies.append(
                        f"Performance is {abs(deviation_pct):.1f}% {direction} than historical average"
                    )

        # Broadcast completion
        await ws_manager.broadcast({
            "type": "profile_complete",
            "query_hash": query_hash,
            "status": "success",
            "summary": {
                "iterations": len(successful_runs),
                "avg_time_ms": exec_stats.get("mean"),
                "anomalies": anomalies
            }
        })

        return ProfileResponse(
            query_hash=query_hash,
            query=request.sql,
            status="success",
            iterations_requested=request.iterations,
            iterations_successful=len(successful_runs),
            execution_time_distribution=exec_stats,
            cost_analysis=cost_analysis,
            cache_analysis=cache_analysis,
            historical_comparison=historical_stats if historical_stats.get("sample_count", 0) > 0 else None,
            anomalies_detected=anomalies,
            results=results
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Profiling failed: {str(e)}")


@router.post("/statistics", response_model=Dict[str, Any])
async def get_query_statistics(request: QueryStatisticsRequest):
    """
    Get statistical analysis and historical data for a specific query.

    Provides:
    - Execution time statistics (mean, median, percentiles)
    - Cost analysis
    - Cache hit rate trends
    - Performance trend analysis
    - Recent alerts
    """
    if not settings.PROFILER_ENABLED:
        raise HTTPException(status_code=503, detail="Profiler is disabled")

    if not request.sql and not request.query_hash:
        raise HTTPException(
            status_code=400,
            detail="Either 'sql' or 'query_hash' must be provided"
        )

    try:
        profiler = get_profiler()
        stats = profiler.get_query_statistics(
            query=request.sql,
            query_hash=request.query_hash,
            hours=request.hours
        )
        return stats

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve statistics: {str(e)}"
        )


@router.get("/summaries", response_model=QuerySummaryResponse)
async def get_query_summaries(
    hours: int = 24,
    limit: int = 100
):
    """
    Get summaries for all tracked queries.

    Returns a list of queries with execution counts and performance metrics
    for the specified time window.
    """
    if not settings.PROFILER_ENABLED:
        raise HTTPException(status_code=503, detail="Profiler is disabled")

    try:
        profiler = get_profiler()
        summaries = profiler.get_all_query_summaries(hours=hours, limit=limit)

        return QuerySummaryResponse(
            summaries=summaries,
            total_queries=len(summaries),
            time_window_hours=hours
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve summaries: {str(e)}"
        )


@router.delete("/cleanup")
async def cleanup_old_data(days: int = 30):
    """
    Clean up old profiling data.

    Removes profiling records older than the specified number of days.
    This helps manage database size and improve query performance.
    """
    if not settings.PROFILER_ENABLED:
        raise HTTPException(status_code=503, detail="Profiler is disabled")

    try:
        profiler = get_profiler()
        deleted_count = profiler.cleanup_old_data(days=days)

        return {
            "status": "success",
            "deleted_records": deleted_count,
            "retention_days": days
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Cleanup failed: {str(e)}"
        )


@router.get("/analysis/recent")
async def get_recent_analysis(limit: int = 10):
    """
    Get recent background analysis results.

    Returns the most recent automated analysis reports generated
    by the background task system.
    """
    if not settings.PROFILER_ENABLED:
        raise HTTPException(status_code=503, detail="Profiler is disabled")

    from app.core.profiler_tasks import get_background_tasks

    try:
        tasks = get_background_tasks()
        results = tasks.get_recent_analysis(limit=limit)

        return {
            "status": "success",
            "count": len(results),
            "results": results
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve analysis: {str(e)}"
        )


@router.post("/analysis/manual/{query_hash}")
async def run_manual_analysis(query_hash: str):
    """
    Run manual analysis for a specific query.

    Generates optimization recommendations based on historical
    performance data for the specified query.
    """
    if not settings.PROFILER_ENABLED:
        raise HTTPException(status_code=503, detail="Profiler is disabled")

    from app.core.profiler_tasks import get_background_tasks

    try:
        tasks = get_background_tasks()
        result = await tasks.run_manual_analysis(query_hash)

        if result.get("status") == "error":
            raise HTTPException(status_code=404, detail=result.get("message"))

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}"
        )


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time profiling updates.

    Clients can connect to receive live updates during query profiling,
    including per-iteration metrics and completion notifications.

    Message types:
    - profile_iteration: Sent after each profiling iteration
    - profile_complete: Sent when profiling finishes
    - ping: Keepalive message
    """
    await ws_manager.connect(websocket)

    try:
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "message": "Connected to QEO Profiler real-time monitoring",
            "profiler_enabled": settings.PROFILER_ENABLED
        })

        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for client messages (e.g., ping/pong)
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=30.0
                )

                # Handle ping
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})

            except asyncio.TimeoutError:
                # Send keepalive
                await websocket.send_json({"type": "ping"})

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        ws_manager.disconnect(websocket)
        print(f"WebSocket error: {e}")
