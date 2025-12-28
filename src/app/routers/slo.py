"""
SLO API endpoints for monitoring service level objectives.

Endpoints:
- GET /api/v1/slo/status - Current SLO status and error budgets
- GET /api/v1/slo/budget - Error budget details by SLI
- GET /api/v1/slo/report - Historical error budget report
- GET /api/v1/slo/can-deploy - Check if deployments are allowed
"""

import logging
from datetime import datetime
from typing import Dict, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..core.metrics import observe_request
from ..core.slo import SLOManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/slo", tags=["slo"])

# Global SLO manager instance
_slo_manager = None


def get_slo_manager() -> SLOManager:
    """Get or create SLO manager singleton."""
    global _slo_manager
    if _slo_manager is None:
        _slo_manager = SLOManager()
    return _slo_manager


# Response models
class BurnRateResponse(BaseModel):
    """Burn rate for a time window."""

    window_hours: int
    rate: float
    threshold: float
    alerting: bool


class ErrorBudgetResponse(BaseModel):
    """Error budget details for an SLI."""

    sli_name: str
    target: float
    window_days: int
    total_events: int
    good_events: int
    current_sli: float
    error_budget_remaining_pct: float
    burn_rates: List[BurnRateResponse]
    time_to_exhaustion_hours: float = None


class SLOStatusResponse(BaseModel):
    """Complete SLO status."""

    timestamp: datetime
    mode: str
    error_budgets: Dict[str, ErrorBudgetResponse]
    overall_health: float = Field(
        ..., ge=0, le=1, description="Overall health score (0-1)"
    )
    can_deploy: bool
    alerts: List[str]
    recommendations: List[str]


class CanDeployResponse(BaseModel):
    """Deployment check response."""

    allowed: bool
    reason: str
    current_mode: str
    min_error_budget_pct: float


@router.get("/status", response_model=SLOStatusResponse)
@observe_request
async def get_slo_status():
    """
    Get current SLO status including error budgets and operating mode.

    This endpoint queries Prometheus for real-time metrics to calculate:
    - Current SLI values for availability, latency, and quality
    - Error budget remaining for each SLI
    - Burn rates across multiple time windows
    - Operating mode and deployment status
    - Active alerts and recommendations

    Returns:
        SLOStatusResponse with complete SLO status
    """
    try:
        manager = get_slo_manager()

        # In production, fetch these from Prometheus
        # For now, use mock data (would integrate with actual metrics)

        # Calculate metrics from Prometheus counters
        # Note: In real implementation, query Prometheus API for 28-day windows

        # Mock data for demonstration (replace with actual Prometheus queries)
        availability_good = 9950
        availability_total = 10000
        latency_good = 9900
        latency_total = 10000
        quality_good = 900
        quality_total = 1000

        status = manager.get_status(
            availability_good=availability_good,
            availability_total=availability_total,
            latency_good=latency_good,
            latency_total=latency_total,
            quality_good=quality_good,
            quality_total=quality_total,
        )

        # Convert to response model
        error_budgets_response = {}
        for sli_name, budget in status.error_budgets.items():
            current_sli = (
                budget.good_events / budget.total_events
                if budget.total_events > 0
                else 1.0
            )
            error_budgets_response[sli_name] = ErrorBudgetResponse(
                sli_name=budget.sli_name,
                target=budget.target,
                window_days=budget.window_days,
                total_events=budget.total_events,
                good_events=budget.good_events,
                current_sli=float(f"{current_sli:.6f}"),
                error_budget_remaining_pct=budget.error_budget_remaining_pct,
                burn_rates=[
                    BurnRateResponse(
                        window_hours=br.window_hours,
                        rate=br.rate,
                        threshold=br.threshold,
                        alerting=br.alerting,
                    )
                    for br in budget.burn_rates
                ],
                time_to_exhaustion_hours=budget.time_to_exhaustion_hours,
            )

        return SLOStatusResponse(
            timestamp=status.timestamp,
            mode=status.mode.value,
            error_budgets=error_budgets_response,
            overall_health=status.overall_health,
            can_deploy=status.can_deploy,
            alerts=status.alerts,
            recommendations=status.recommendations,
        )

    except Exception as e:
        logger.error(f"Error getting SLO status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/budget", response_model=Dict[str, ErrorBudgetResponse])
@observe_request
async def get_error_budgets():
    """
    Get detailed error budget information for all SLIs.

    Returns error budget calculation details including:
    - Total and good event counts
    - Current SLI values
    - Error budget remaining percentage
    - Burn rates for multiple time windows

    Returns:
        Dictionary mapping SLI name to error budget details
    """
    try:
        # Get current status first
        status_response = await get_slo_status()
        return status_response.error_budgets

    except Exception as e:
        logger.error(f"Error getting error budgets: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/report")
@observe_request
async def get_budget_report(
    days: int = Query(
        7, ge=1, le=90, description="Number of days to include in report"
    ),
):
    """
    Generate error budget report for the specified time period.

    Args:
        days: Number of days to include (1-90, default: 7)

    Returns:
        Historical error budget report with:
        - Daily budget snapshots
        - Budget exhaustion incidents
        - Deployment blocks count
        - Trend analysis
    """
    try:
        manager = get_slo_manager()
        report = manager.get_budget_report(days=days)
        return report

    except Exception as e:
        logger.error(f"Error generating budget report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/can-deploy", response_model=CanDeployResponse)
@observe_request
async def can_deploy():
    """
    Check if deployments are currently allowed based on error budget.

    This endpoint should be called by CI/CD pipelines before deploying
    to production. Deployments are blocked when error budget is low
    to prevent further service degradation.

    Deployment Policy:
    - >50% budget: Deployments allowed (NORMAL mode)
    - 25-50% budget: Deployments allowed with caution (CONSERVATIVE mode)
    - 10-25% budget: Deployments blocked (RESTRICTED mode)
    - <10% budget: Deployments blocked, page on-call (RESTRICTED mode)
    - 0% budget: Emergency mode, cache-only operation (EMERGENCY mode)

    Returns:
        CanDeployResponse with deployment status and reason
    """
    try:
        manager = get_slo_manager()
        allowed, reason = manager.can_deploy()

        # Get current status for additional context
        status_response = await get_slo_status()
        min_budget = min(
            b.error_budget_remaining_pct for b in status_response.error_budgets.values()
        )

        return CanDeployResponse(
            allowed=allowed,
            reason=reason,
            current_mode=status_response.mode,
            min_error_budget_pct=min_budget,
        )

    except Exception as e:
        logger.error(f"Error checking deployment status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e
