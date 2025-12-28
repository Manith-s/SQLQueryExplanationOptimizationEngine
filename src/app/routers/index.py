"""
Index Management API Router

Provides comprehensive index lifecycle management, automated recommendations,
self-healing capabilities, and advanced analytics.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.index_manager import get_index_manager
from app.core.self_healing import ActionStatus, get_self_healing_manager
from app.core.stats_collector import get_stats_collector

router = APIRouter(prefix="/api/v1/index", tags=["index-management"])


# Request/Response Models
class AnalyzeRequest(BaseModel):
    """Request for comprehensive index analysis."""
    schema: str = Field(default="public", description="Database schema to analyze")
    tables: Optional[List[str]] = Field(None, description="Specific tables to analyze (or None for all)")
    include_stats: bool = Field(default=True, description="Include detailed statistics")
    include_recommendations: bool = Field(default=True, description="Generate recommendations")


class AnalyzeResponse(BaseModel):
    """Response from index analysis."""
    schema: str
    total_indexes: int
    unused_indexes: int
    redundant_pairs: int
    health_score: int
    indexes: List[Dict[str, Any]]
    recommendations: Optional[List[Dict[str, Any]]] = None
    table_statistics: Optional[Dict[str, Any]] = None


class RecommendRequest(BaseModel):
    """Request for index recommendations."""
    schema: str = Field(default="public")
    tables: Optional[List[str]] = None
    query_patterns: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Query patterns to analyze for recommendations"
    )
    min_priority: int = Field(default=5, ge=1, le=10)
    include_drops: bool = Field(default=True)


class RecommendResponse(BaseModel):
    """Response with index recommendations."""
    recommendations: List[Dict[str, Any]]
    total_recommendations: int
    high_priority_count: int
    estimated_total_benefit: float
    estimated_total_cost_mb: float


class ImpactRequest(BaseModel):
    """Request for impact estimation."""
    schema: str = Field(default="public")
    table_name: str
    index_type: str = Field(default="btree")
    columns: List[str]
    where_clause: Optional[str] = None
    analyze_workload: bool = Field(default=False)


class ImpactResponse(BaseModel):
    """Response with impact estimation."""
    estimated_size_mb: float
    estimated_creation_time_seconds: float
    estimated_benefit_score: float
    maintenance_cost_score: float
    recommendation: str
    ddl_statement: str


class HealthResponse(BaseModel):
    """Response with index health metrics."""
    overall_health_score: int
    index_health: Dict[str, Any]
    performance_health: Dict[str, Any]
    recommendations: List[str]
    recent_issues: List[Dict[str, Any]]


class AutoTuneRequest(BaseModel):
    """Request to enable auto-tuning."""
    schema: str = Field(default="public")
    dry_run: bool = Field(default=True, description="Run in simulation mode")
    auto_approve: bool = Field(default=False, description="Auto-approve low-risk changes")
    performance_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
    schedule_interval_hours: int = Field(default=24, ge=1, le=168)


class AutoTuneResponse(BaseModel):
    """Response from auto-tune configuration."""
    enabled: bool
    configuration: Dict[str, Any]
    next_run_scheduled: Optional[str]
    healing_actions_count: int


# API Endpoints

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_indexes(request: AnalyzeRequest):
    """
    Perform comprehensive index analysis.

    Analyzes index usage, identifies unused and redundant indexes,
    and generates health metrics.
    """
    try:
        mgr = get_index_manager(request.schema)

        # Get all index metrics
        all_indexes = mgr.get_index_usage_stats()
        unused = mgr.identify_unused_indexes()
        redundant = mgr.identify_redundant_indexes()

        # Calculate health score
        health_summary = mgr.get_index_health_summary()

        # Prepare index data
        indexes_data = [
            {
                "name": idx.index_name,
                "table": idx.table_name,
                "type": idx.index_type,
                "columns": idx.columns,
                "size_mb": float(f"{idx.size_bytes / (1024*1024):.2f}"),
                "scans": idx.scans,
                "effectiveness_score": idx.effectiveness_score,
                "scan_efficiency": idx.scan_efficiency,
                "usage_frequency": idx.usage_frequency,
                "maintenance_cost": idx.maintenance_cost,
                "is_primary": idx.is_primary,
                "is_unused": idx in unused
            }
            for idx in all_indexes
        ]

        response_data = {
            "schema": request.schema,
            "total_indexes": len(all_indexes),
            "unused_indexes": len(unused),
            "redundant_pairs": len(redundant),
            "health_score": health_summary["health_score"],
            "indexes": indexes_data
        }

        # Add recommendations if requested
        if request.include_recommendations:
            recommendations = mgr.generate_recommendations()
            response_data["recommendations"] = [
                {
                    "action": rec.action,
                    "priority": rec.priority,
                    "table": rec.table_name,
                    "index_type": rec.index_type,
                    "columns": rec.columns,
                    "rationale": rec.rationale,
                    "estimated_benefit": rec.estimated_benefit,
                    "confidence": rec.confidence,
                    "ddl": rec.to_ddl(request.schema)
                }
                for rec in recommendations
            ]

        # Add detailed statistics if requested
        if request.include_stats:
            collector = get_stats_collector(request.schema)
            tables_to_analyze = request.tables if request.tables else [idx.table_name for idx in all_indexes[:5]]

            table_stats = {}
            for table in tables_to_analyze:
                stats = collector.collect_table_statistics(table)
                if stats:
                    table_stats[table] = {
                        "row_count": stats[0].row_count,
                        "size_mb": float(f"{stats[0].total_size_bytes / (1024*1024):.2f}"),
                        "dead_tuples": stats[0].n_dead_tup,
                        "last_analyze": stats[0].last_analyze.isoformat() if stats[0].last_analyze else None
                    }

            response_data["table_statistics"] = table_stats

        return AnalyzeResponse(**response_data)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}") from e


@router.post("/recommend", response_model=RecommendResponse)
async def recommend_indexes(request: RecommendRequest):
    """
    Generate prioritized index recommendations.

    Analyzes current indexes and query patterns to suggest
    optimal index configurations.
    """
    try:
        mgr = get_index_manager(request.schema)

        # Generate recommendations
        recommendations = mgr.generate_recommendations(
            query_patterns=request.query_patterns
        )

        # Filter by priority
        filtered_recs = [r for r in recommendations if r.priority >= request.min_priority]

        if not request.include_drops:
            filtered_recs = [r for r in filtered_recs if r.action != "drop"]

        # Calculate totals
        high_priority = [r for r in filtered_recs if r.priority >= 8]
        total_benefit = sum(r.estimated_benefit for r in filtered_recs)
        total_cost_mb = sum(r.estimated_cost_bytes for r in filtered_recs) / (1024 * 1024)

        # Format response
        recommendations_data = [
            {
                "action": rec.action,
                "priority": rec.priority,
                "table": rec.table_name,
                "index_type": rec.index_type,
                "columns": rec.columns,
                "where_clause": rec.where_clause,
                "expression": rec.expression,
                "rationale": rec.rationale,
                "estimated_benefit": rec.estimated_benefit,
                "estimated_cost_mb": float(f"{rec.estimated_cost_bytes / (1024*1024):.2f}"),
                "confidence": rec.confidence,
                "ddl": rec.to_ddl(request.schema)
            }
            for rec in filtered_recs
        ]

        return RecommendResponse(
            recommendations=recommendations_data,
            total_recommendations=len(filtered_recs),
            high_priority_count=len(high_priority),
            estimated_total_benefit=float(f"{total_benefit:.2f}"),
            estimated_total_cost_mb=float(f"{total_cost_mb:.2f}")
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Recommendation failed: {str(e)}") from e


@router.post("/impact", response_model=ImpactResponse)
async def estimate_impact(request: ImpactRequest):
    """
    Estimate impact of creating a specific index.

    Analyzes table size, data distribution, and usage patterns
    to predict index creation cost and benefit.
    """
    try:
        collector = get_stats_collector(request.schema)

        # Get table statistics
        table_stats = collector.collect_table_statistics(request.table_name)
        if not table_stats:
            raise HTTPException(status_code=404, detail="Table not found")

        stats = table_stats[0]

        # Estimate index size (rough approximation)
        # Typical btree index is 20-30% of table size for multi-column
        size_factor = 0.25 if len(request.columns) > 1 else 0.15
        estimated_size_bytes = stats.total_size_bytes * size_factor

        # Estimate creation time (very rough: ~1MB per second)
        estimated_time_seconds = (estimated_size_bytes / (1024 * 1024)) / 10

        # Get column statistics for benefit estimation
        col_stats = collector.collect_column_statistics(request.table_name)
        relevant_cols = [c for c in col_stats if c.column_name in request.columns]

        # Calculate benefit score based on column characteristics
        benefit_score = 0.0
        for col in relevant_cols:
            # High cardinality is good
            if col.n_distinct > 100:
                benefit_score += 30
            # Good correlation is beneficial
            if col.correlation and abs(col.correlation) > 0.7:
                benefit_score += 20
            # Low null fraction is good
            if col.null_frac < 0.1:
                benefit_score += 10

        # Maintenance cost estimate
        maintenance_cost = estimated_size_bytes / stats.total_size_bytes

        # Generate recommendation
        if benefit_score > 50 and maintenance_cost < 0.5:
            recommendation = "Highly recommended - good benefit/cost ratio"
        elif benefit_score > 30:
            recommendation = "Recommended - moderate benefit expected"
        else:
            recommendation = "Consider carefully - benefit may be limited"

        # Generate DDL
        idx_name = f"idx_{request.table_name}_{'_'.join(request.columns)}"
        col_spec = ", ".join(request.columns)
        using_clause = f"USING {request.index_type.upper()}" if request.index_type != "btree" else ""
        where_clause = f"WHERE {request.where_clause}" if request.where_clause else ""

        ddl = (
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {idx_name} "
            f"ON {request.schema}.{request.table_name} {using_clause} "
            f"({col_spec}) {where_clause}".strip()
        )

        return ImpactResponse(
            estimated_size_mb=float(f"{estimated_size_bytes / (1024*1024):.2f}"),
            estimated_creation_time_seconds=float(f"{estimated_time_seconds:.1f}"),
            estimated_benefit_score=float(f"{benefit_score:.1f}"),
            maintenance_cost_score=float(f"{maintenance_cost:.3f}"),
            recommendation=recommendation,
            ddl_statement=ddl
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Impact analysis failed: {str(e)}") from e


@router.get("/health", response_model=HealthResponse)
async def get_index_health(schema: str = Query(default="public")):
    """
    Get comprehensive index health metrics.

    Returns overall health scores, performance metrics,
    and recommendations for improvement.
    """
    try:
        # Get self-healing health status
        healing_mgr = get_self_healing_manager(schema)
        health_status = healing_mgr.get_health_status()

        # Get index-specific health
        index_mgr = get_index_manager(schema)
        index_health = index_mgr.get_index_health_summary()

        # Identify recent issues
        recent_issues = []
        if index_health["unused_indexes"] > 0:
            recent_issues.append({
                "severity": "warning",
                "type": "unused_indexes",
                "count": index_health["unused_indexes"],
                "message": f"{index_health['unused_indexes']} unused indexes consuming {index_health.get('unused_size_mb', 0)}MB"
            })

        if index_health["redundant_pairs"] > 0:
            recent_issues.append({
                "severity": "info",
                "type": "redundant_indexes",
                "count": index_health["redundant_pairs"],
                "message": f"{index_health['redundant_pairs']} redundant index pairs detected"
            })

        # Generate recommendations
        recommendations = []
        if index_health["health_score"] < 70:
            recommendations.append("Run index analysis to identify optimization opportunities")
        if health_status["performance"]["severity"] != "ok":
            recommendations.append("Performance degradation detected - consider automated optimization")
        if index_health["unused_indexes"] > 5:
            recommendations.append("Multiple unused indexes found - review for removal")

        return HealthResponse(
            overall_health_score=index_health["health_score"],
            index_health=index_health,
            performance_health=health_status["performance"],
            recommendations=recommendations if recommendations else ["System health is good"],
            recent_issues=recent_issues
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}") from e


@router.post("/auto-tune", response_model=AutoTuneResponse)
async def enable_auto_tune(
    request: AutoTuneRequest,
    background_tasks: BackgroundTasks
):
    """
    Enable or configure automatic index management.

    Activates self-healing capabilities with specified parameters.
    """
    try:
        healing_mgr = get_self_healing_manager(
            schema=request.schema,
            auto_approve=request.auto_approve,
            dry_run=request.dry_run
        )

        # Monitor performance
        severity, perf_summary = healing_mgr.monitor_query_performance()

        # Trigger healing if needed
        healing_action = None
        if severity.value in ["critical", "warning"]:
            healing_action = healing_mgr.trigger_healing_action(
                reason=f"Performance degradation detected: {severity.value}",
                dry_run=request.dry_run
            )

            # If not dry-run and auto-approve, execute in background
            if not request.dry_run and request.auto_approve and healing_action:
                background_tasks.add_task(
                    healing_mgr.execute_healing_action,
                    healing_action.action_id,
                    "auto_approve_system"
                )

        # Get action history
        action_history = healing_mgr.get_action_history(limit=10)

        return AutoTuneResponse(
            enabled=not request.dry_run,
            configuration={
                "schema": request.schema,
                "dry_run": request.dry_run,
                "auto_approve": request.auto_approve,
                "performance_threshold": request.performance_threshold,
                "schedule_interval_hours": request.schedule_interval_hours,
                "current_performance": severity.value
            },
            next_run_scheduled=None,  # Would be set by scheduler
            healing_actions_count=len(action_history)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auto-tune configuration failed: {str(e)}") from e


@router.get("/actions")
async def get_healing_actions(
    schema: str = Query(default="public"),
    limit: int = Query(default=50, ge=1, le=200),
    status: Optional[str] = Query(default=None)
):
    """
    Get history of automated healing actions.

    Returns list of all automated index management actions
    with their status and results.
    """
    try:
        healing_mgr = get_self_healing_manager(schema)

        status_filter = ActionStatus[status.upper()] if status else None
        actions = healing_mgr.get_action_history(limit=limit, status_filter=status_filter)

        return {
            "actions": actions,
            "total": len(actions),
            "pending_approval": len([a for a in actions if a["status"] == "pending"]),
            "completed": len([a for a in actions if a["status"] == "completed"])
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve actions: {str(e)}") from e


@router.post("/actions/{action_id}/execute")
async def execute_action(
    action_id: str,
    approved_by: Optional[str] = Query(default=None),
    schema: str = Query(default="public")
):
    """
    Execute a pending healing action.

    Requires action_id and optional approver information.
    """
    try:
        healing_mgr = get_self_healing_manager(schema)
        result = healing_mgr.execute_healing_action(action_id, approved_by)

        return {
            "action_id": action_id,
            "result": result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution failed: {str(e)}") from e


@router.post("/actions/{action_id}/rollback")
async def rollback_action(
    action_id: str,
    schema: str = Query(default="public")
):
    """
    Rollback a completed healing action.

    Reverses the changes made by a previous action.
    """
    try:
        healing_mgr = get_self_healing_manager(schema)
        result = healing_mgr.rollback_action(action_id)

        return {
            "action_id": action_id,
            "rollback_result": result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rollback failed: {str(e)}") from e


@router.get("/statistics/{table_name}")
async def get_table_statistics(
    table_name: str,
    schema: str = Query(default="public"),
    include_columns: bool = Query(default=True),
    include_growth: bool = Query(default=True),
    include_bloat: bool = Query(default=True)
):
    """
    Get comprehensive statistics for a specific table.

    Returns detailed table and column statistics for
    informed index decisions.
    """
    try:
        collector = get_stats_collector(schema)

        if include_columns:
            analysis = collector.get_comprehensive_analysis(table_name)
            return analysis
        else:
            table_stats = collector.collect_table_statistics(table_name)
            if not table_stats:
                raise HTTPException(status_code=404, detail="Table not found")

            return {
                "table_name": table_name,
                "statistics": {
                    "row_count": table_stats[0].row_count,
                    "size_mb": float(f"{table_stats[0].total_size_bytes / (1024*1024):.2f}"),
                    "index_size_mb": float(f"{table_stats[0].index_size_bytes / (1024*1024):.2f}"),
                    "dead_tuples": table_stats[0].n_dead_tup
                }
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Statistics collection failed: {str(e)}") from e
