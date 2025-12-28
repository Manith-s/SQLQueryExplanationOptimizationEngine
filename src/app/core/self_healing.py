"""
Self-Healing Index Management System

Monitors database performance in real-time and automatically triggers
optimizations when degradation is detected. Includes rollback capabilities
and comprehensive audit logging.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.db import get_conn
from app.core.index_manager import IndexRecommendation, get_index_manager


class ActionStatus(Enum):
    """Status of automated actions."""
    PENDING = "pending"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class PerformanceThreshold(Enum):
    """Performance degradation severity levels."""
    CRITICAL = "critical"  # >50% degradation
    WARNING = "warning"    # 25-50% degradation
    INFO = "info"          # 10-25% degradation
    OK = "ok"              # <10% degradation


@dataclass
class PerformanceMetric:
    """Performance metric snapshot."""
    timestamp: datetime
    metric_name: str
    value: float
    table_name: Optional[str] = None
    query_hash: Optional[str] = None


@dataclass
class HealingAction:
    """Represents a self-healing action."""
    action_id: str
    timestamp: datetime
    status: ActionStatus
    trigger_reason: str
    recommendations: List[IndexRecommendation]
    dry_run: bool
    approval_required: bool
    approved_by: Optional[str] = None
    executed_at: Optional[datetime] = None
    rollback_sql: Optional[List[str]] = None
    result_summary: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class SelfHealingManager:
    """
    Manages automated performance monitoring and healing actions.

    Monitors query performance, detects degradation, and automatically
    triggers index optimization when needed.
    """

    def __init__(
        self,
        schema: str = "public",
        auto_approve: bool = False,
        dry_run_default: bool = True
    ):
        self.schema = schema
        self.auto_approve = auto_approve
        self.dry_run_default = dry_run_default

        # Performance thresholds
        self.degradation_threshold = float(
            settings.__dict__.get("HEALING_DEGRADATION_THRESHOLD", 0.25)  # 25%
        )
        self.critical_threshold = float(
            settings.__dict__.get("HEALING_CRITICAL_THRESHOLD", 0.50)  # 50%
        )

        # Action history
        self.action_history: List[HealingAction] = []
        self._load_action_history()

    def monitor_query_performance(
        self,
        time_window_minutes: int = 60
    ) -> Tuple[PerformanceThreshold, Dict[str, Any]]:
        """
        Monitor recent query performance and detect degradation.

        Args:
            time_window_minutes: Time window to analyze

        Returns:
            Tuple of (severity_level, performance_summary)
        """
        try:
            # Query pg_stat_statements for recent performance
            query = """
            SELECT
                queryid,
                query,
                calls,
                total_exec_time,
                mean_exec_time,
                stddev_exec_time,
                rows
            FROM pg_stat_statements
            WHERE query NOT LIKE '%pg_stat%'
            ORDER BY mean_exec_time DESC
            LIMIT 100;
            """

            with get_conn() as conn:
                with conn.cursor() as cur:
                    try:
                        cur.execute(query)
                        rows = cur.fetchall()
                    except Exception as e:
                        # pg_stat_statements may not be enabled
                        print(f"pg_stat_statements not available: {e}")
                        return PerformanceThreshold.OK, {"available": False}

            # Analyze performance metrics
            if not rows:
                return PerformanceThreshold.OK, {"queries_analyzed": 0}

            # Calculate metrics
            total_queries = len(rows)
            slow_queries = [r for r in rows if r[4] > 1000]  # > 1 second mean time
            avg_time = sum(r[4] for r in rows) / total_queries

            # Detect degradation by comparing to baseline
            degradation_score = self._calculate_degradation_score(rows)

            # Determine severity
            if degradation_score > self.critical_threshold:
                severity = PerformanceThreshold.CRITICAL
            elif degradation_score > self.degradation_threshold:
                severity = PerformanceThreshold.WARNING
            elif degradation_score > 0.10:
                severity = PerformanceThreshold.INFO
            else:
                severity = PerformanceThreshold.OK

            summary = {
                "severity": severity.value,
                "degradation_score": float(f"{degradation_score:.3f}"),
                "total_queries": total_queries,
                "slow_queries": len(slow_queries),
                "avg_execution_time_ms": float(f"{avg_time:.2f}"),
                "queries_analyzed": total_queries,
                "recommendations": []
            }

            # Add slow query details
            if slow_queries:
                summary["slowest_queries"] = [
                    {
                        "query_id": str(r[0]),
                        "query_preview": r[1][:100] + "..." if len(r[1]) > 100 else r[1],
                        "calls": r[2],
                        "mean_time_ms": float(f"{r[4]:.2f}")
                    }
                    for r in slow_queries[:5]
                ]

            return severity, summary

        except Exception as e:
            print(f"Error monitoring performance: {e}")
            return PerformanceThreshold.OK, {"error": str(e)}

    def _calculate_degradation_score(self, query_stats: List[Tuple]) -> float:
        """
        Calculate overall degradation score based on query statistics.

        This is a simplified version - in production, you'd compare
        against historical baselines.
        """
        if not query_stats:
            return 0.0

        # Simple heuristic: ratio of slow queries to total
        slow_count = sum(1 for r in query_stats if r[4] > 1000)  # > 1 second
        total_count = len(query_stats)

        # Factor in variance (high stddev indicates inconsistent performance)
        high_variance = sum(1 for r in query_stats if r[5] and r[5] > r[4] * 0.5)

        degradation = (slow_count / total_count) * 0.7 + (high_variance / total_count) * 0.3
        return float(f"{degradation:.3f}")

    def trigger_healing_action(
        self,
        reason: str,
        dry_run: Optional[bool] = None,
        query_patterns: Optional[List[Dict[str, Any]]] = None
    ) -> HealingAction:
        """
        Trigger a self-healing action based on detected issues.

        Args:
            reason: Why the healing action was triggered
            dry_run: Whether to only simulate (defaults to class setting)
            query_patterns: Query patterns for analysis

        Returns:
            HealingAction object
        """
        # Generate unique action ID
        action_id = self._generate_action_id()

        # Get index recommendations
        index_mgr = get_index_manager(self.schema)
        recommendations = index_mgr.generate_recommendations(query_patterns)

        # Create healing action
        action = HealingAction(
            action_id=action_id,
            timestamp=datetime.utcnow(),
            status=ActionStatus.PENDING,
            trigger_reason=reason,
            recommendations=recommendations,
            dry_run=dry_run if dry_run is not None else self.dry_run_default,
            approval_required=not self.auto_approve
        )

        # Store in history
        self.action_history.append(action)
        self._save_action_to_audit_log(action)

        # Auto-approve if enabled and not critical
        if self.auto_approve and not action.dry_run:
            action.status = ActionStatus.APPROVED
            action.approved_by = "system_auto_approve"

        return action

    def execute_healing_action(
        self,
        action_id: str,
        approved_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute a healing action.

        Args:
            action_id: ID of the action to execute
            approved_by: Who approved the action

        Returns:
            Execution result summary
        """
        # Find action
        action = next((a for a in self.action_history if a.action_id == action_id), None)
        if not action:
            return {"success": False, "error": "Action not found"}

        # Check if already executed
        if action.status in [ActionStatus.COMPLETED, ActionStatus.EXECUTING]:
            return {"success": False, "error": "Action already executed or executing"}

        # Require approval if needed
        if action.approval_required and action.status != ActionStatus.APPROVED:
            if not approved_by:
                return {"success": False, "error": "Approval required"}
            action.approved_by = approved_by
            action.status = ActionStatus.APPROVED

        # Execute in dry-run mode
        if action.dry_run:
            return self._simulate_execution(action)

        # Execute for real
        return self._execute_recommendations(action)

    def _simulate_execution(self, action: HealingAction) -> Dict[str, Any]:
        """Simulate execution of recommendations (dry-run)."""
        results = {
            "success": True,
            "dry_run": True,
            "action_id": action.action_id,
            "recommendations_count": len(action.recommendations),
            "estimated_impact": {},
            "ddl_statements": []
        }

        total_benefit = 0.0
        total_cost = 0

        for rec in action.recommendations:
            ddl = rec.to_ddl(self.schema)
            results["ddl_statements"].append({
                "action": rec.action,
                "table": rec.table_name,
                "priority": rec.priority,
                "sql": ddl,
                "rationale": rec.rationale
            })

            total_benefit += rec.estimated_benefit
            total_cost += rec.estimated_cost_bytes

        results["estimated_impact"] = {
            "total_benefit_score": float(f"{total_benefit:.2f}"),
            "total_cost_bytes": total_cost,
            "total_cost_mb": float(f"{total_cost / (1024 * 1024):.2f}")
        }

        action.status = ActionStatus.COMPLETED
        action.result_summary = results

        return results

    def _execute_recommendations(self, action: HealingAction) -> Dict[str, Any]:
        """
        Execute recommendations for real (DANGEROUS - requires approval).

        NOTE: This modifies the database. Use with caution.
        """
        action.status = ActionStatus.EXECUTING
        action.executed_at = datetime.utcnow()

        results = {
            "success": True,
            "dry_run": False,
            "action_id": action.action_id,
            "executed_recommendations": [],
            "failed_recommendations": [],
            "rollback_sql": []
        }

        rollback_statements = []

        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    for rec in action.recommendations:
                        try:
                            ddl = rec.to_ddl(self.schema)

                            # Generate rollback SQL
                            if rec.action == "create":
                                idx_name = ddl.split("IF NOT EXISTS")[1].split("ON")[0].strip()
                                rollback = f"DROP INDEX CONCURRENTLY IF EXISTS {self.schema}.{idx_name}"
                                rollback_statements.append(rollback)
                            elif rec.action == "drop":
                                # For drops, would need to store the original definition
                                rollback_statements.append(f"-- Cannot rollback DROP: {rec.columns[0]}")

                            # Execute DDL
                            cur.execute(ddl)
                            conn.commit()

                            results["executed_recommendations"].append({
                                "action": rec.action,
                                "table": rec.table_name,
                                "sql": ddl,
                                "status": "success"
                            })

                        except Exception as e:
                            conn.rollback()
                            results["failed_recommendations"].append({
                                "action": rec.action,
                                "table": rec.table_name,
                                "error": str(e)
                            })

            action.status = ActionStatus.COMPLETED
            action.rollback_sql = rollback_statements
            results["rollback_sql"] = rollback_statements

        except Exception as e:
            action.status = ActionStatus.FAILED
            action.error_message = str(e)
            results["success"] = False
            results["error"] = str(e)

        action.result_summary = results
        self._save_action_to_audit_log(action)

        return results

    def rollback_action(self, action_id: str) -> Dict[str, Any]:
        """
        Rollback a previously executed action.

        Args:
            action_id: ID of action to rollback

        Returns:
            Rollback result summary
        """
        action = next((a for a in self.action_history if a.action_id == action_id), None)
        if not action:
            return {"success": False, "error": "Action not found"}

        if action.status != ActionStatus.COMPLETED:
            return {"success": False, "error": "Only completed actions can be rolled back"}

        if not action.rollback_sql:
            return {"success": False, "error": "No rollback SQL available"}

        results = {
            "success": True,
            "action_id": action_id,
            "rollback_statements_executed": [],
            "errors": []
        }

        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    for sql in action.rollback_sql:
                        try:
                            cur.execute(sql)
                            conn.commit()
                            results["rollback_statements_executed"].append(sql)
                        except Exception as e:
                            conn.rollback()
                            results["errors"].append({
                                "sql": sql,
                                "error": str(e)
                            })

            if not results["errors"]:
                action.status = ActionStatus.ROLLED_BACK
            else:
                results["success"] = False

        except Exception as e:
            results["success"] = False
            results["error"] = str(e)

        self._save_action_to_audit_log(action)
        return results

    def get_action_history(
        self,
        limit: int = 50,
        status_filter: Optional[ActionStatus] = None
    ) -> List[Dict[str, Any]]:
        """Get history of healing actions."""
        filtered = self.action_history
        if status_filter:
            filtered = [a for a in filtered if a.status == status_filter]

        # Sort by timestamp (most recent first)
        sorted_actions = sorted(filtered, key=lambda x: x.timestamp, reverse=True)[:limit]

        return [
            {
                "action_id": a.action_id,
                "timestamp": a.timestamp.isoformat(),
                "status": a.status.value,
                "trigger_reason": a.trigger_reason,
                "recommendations_count": len(a.recommendations),
                "dry_run": a.dry_run,
                "approved_by": a.approved_by,
                "executed_at": a.executed_at.isoformat() if a.executed_at else None,
                "result_summary": a.result_summary
            }
            for a in sorted_actions
        ]

    def _generate_action_id(self) -> str:
        """Generate unique action ID."""
        timestamp = datetime.utcnow().isoformat()
        hash_input = f"{timestamp}_{len(self.action_history)}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    def _save_action_to_audit_log(self, action: HealingAction) -> None:
        """Save action to audit log (could be database, file, etc.)."""
        # In a production system, this would write to a proper audit log
        # For now, just store in memory
        log_entry = {
            "action_id": action.action_id,
            "timestamp": action.timestamp.isoformat(),
            "status": action.status.value,
            "trigger_reason": action.trigger_reason,
            "dry_run": action.dry_run,
            "approval_required": action.approval_required,
            "approved_by": action.approved_by,
            "executed_at": action.executed_at.isoformat() if action.executed_at else None,
            "result_summary": action.result_summary,
            "error_message": action.error_message
        }

        # Could write to file or database here
        print(f"[AUDIT] {json.dumps(log_entry)}")

    def _load_action_history(self) -> None:
        """Load action history from persistent storage."""
        # In production, load from database
        # For now, start with empty history
        pass

    def get_health_status(self) -> Dict[str, Any]:
        """Get overall system health status."""
        severity, perf_summary = self.monitor_query_performance()

        # Get index health
        index_mgr = get_index_manager(self.schema)
        index_health = index_mgr.get_index_health_summary()

        # Recent actions
        recent_actions = self.get_action_history(limit=10)
        failed_actions = [a for a in recent_actions if a["status"] == "failed"]

        return {
            "overall_status": severity.value,
            "performance": perf_summary,
            "index_health": index_health,
            "recent_actions": len(recent_actions),
            "failed_actions": len(failed_actions),
            "auto_healing_enabled": not self.dry_run_default,
            "last_check": datetime.utcnow().isoformat()
        }


def get_self_healing_manager(
    schema: str = "public",
    auto_approve: bool = False,
    dry_run: bool = True
) -> SelfHealingManager:
    """Factory function to get self-healing manager instance."""
    return SelfHealingManager(schema, auto_approve, dry_run)
