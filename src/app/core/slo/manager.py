"""
SLO Manager: Comprehensive Service Level Objective tracking and enforcement.

Monitors:
- Availability SLI: successful requests / total requests
- Latency SLI: requests under 1s / total requests
- Optimization Quality SLI: improved queries / total optimizations

Features:
- 28-day rolling window error budget calculation
- Multi-window burn rate monitoring (1h, 6h, 24h, 72h)
- Automatic responses based on budget exhaustion
- Emergency mode activation at 0% budget
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple

from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

# Prometheus metrics for SLO tracking
slo_availability = Gauge(
    "qeo_slo_availability",
    "Current availability SLI (successful requests / total)",
)
slo_latency = Gauge(
    "qeo_slo_latency",
    "Current latency SLI (requests under 1s / total)",
)
slo_quality = Gauge(
    "qeo_slo_optimization_quality",
    "Current optimization quality SLI (improved queries / total)",
)
slo_error_budget_remaining = Gauge(
    "qeo_slo_error_budget_remaining_pct",
    "Error budget remaining percentage",
    ["sli"],
)
slo_burn_rate = Gauge(
    "qeo_slo_burn_rate",
    "Error budget burn rate",
    ["sli", "window"],
)
slo_mode = Gauge(
    "qeo_slo_mode",
    "Current SLO mode: 0=normal, 1=conservative, 2=emergency",
)
slo_deployment_blocked = Counter(
    "qeo_slo_deployment_blocked_total",
    "Number of deployments blocked due to low error budget",
)


class ConservativeMode(str, Enum):
    """Operating modes based on error budget."""

    NORMAL = "normal"  # >50% budget
    CONSERVATIVE = "conservative"  # 25-50% budget
    RESTRICTED = "restricted"  # 10-25% budget
    EMERGENCY = "emergency"  # <10% budget or 0% for any SLI


@dataclass
class BurnRate:
    """Burn rate for a specific time window."""

    window_hours: int
    rate: float  # How fast we're consuming error budget (1.0 = normal, >1.0 = faster)
    threshold: float  # Alert threshold
    alerting: bool


@dataclass
class ErrorBudget:
    """Error budget tracking for an SLI."""

    sli_name: str
    target: float  # e.g., 0.995 for 99.5%
    window_days: int  # e.g., 28 days
    total_events: int
    good_events: int
    error_budget_remaining_pct: float
    burn_rates: List[BurnRate]
    time_to_exhaustion_hours: Optional[float]  # None if not exhausting


@dataclass
class SLOStatus:
    """Complete SLO status snapshot."""

    timestamp: datetime
    mode: ConservativeMode
    error_budgets: Dict[str, ErrorBudget]
    overall_health: float  # 0-1 score
    can_deploy: bool
    alerts: List[str]
    recommendations: List[str]


class SLOManager:
    """
    Manages SLOs, error budgets, and automatic responses.

    SLO Targets (28-day windows):
    - Availability: 99.5% (43.2 minutes downtime allowed)
    - Latency: 99% of requests < 1s
    - Quality: 90% of optimizations show improvement

    Burn Rate Windows:
    - 1h: Fast burn detection
    - 6h: Short-term trend
    - 24h: Daily pattern
    - 72h: Multi-day trend
    """

    # SLO targets
    AVAILABILITY_TARGET = 0.995  # 99.5%
    LATENCY_TARGET = 0.99  # 99%
    QUALITY_TARGET = 0.90  # 90%
    WINDOW_DAYS = 28

    # Burn rate thresholds (multiples of normal consumption rate)
    BURN_RATE_THRESHOLDS = {
        1: 14.4,  # 1h window: alert if burning 14.4x normal rate
        6: 6.0,  # 6h window: alert if burning 6x normal rate
        24: 3.0,  # 24h window: alert if burning 3x normal rate
        72: 1.5,  # 72h window: alert if burning 1.5x normal rate
    }

    def __init__(self):
        self._mode = ConservativeMode.NORMAL
        self._deployment_blocked = False
        self._last_page_sent = {}  # Track when we last paged for each SLI
        logger.info("SLOManager initialized")

    def calculate_sli(
        self,
        good_events: int,
        total_events: int,
    ) -> float:
        """Calculate SLI value (good events / total events)."""
        if total_events == 0:
            return 1.0
        return float(f"{good_events / total_events:.6f}")

    def calculate_error_budget(
        self,
        sli_name: str,
        target: float,
        good_events: int,
        total_events: int,
        window_days: int = WINDOW_DAYS,
    ) -> ErrorBudget:
        """
        Calculate error budget for an SLI.

        Error budget = (total - good_threshold) / total
        where good_threshold = target * total

        Example: 99.5% target over 10000 requests
        - good_threshold = 0.995 * 10000 = 9950
        - If we have 9900 good requests: (10000 - 9950) / 10000 = 0.5% budget used
        - Budget remaining = 1 - (bad_events / allowed_bad_events)
        """
        if total_events == 0:
            return ErrorBudget(
                sli_name=sli_name,
                target=target,
                window_days=window_days,
                total_events=0,
                good_events=0,
                error_budget_remaining_pct=100.0,
                burn_rates=[],
                time_to_exhaustion_hours=None,
            )

        current_sli = good_events / total_events
        allowed_bad_events = int((1 - target) * total_events)
        actual_bad_events = total_events - good_events

        if allowed_bad_events == 0:
            # Perfect target (100%), any error exhausts budget
            remaining_pct = 100.0 if actual_bad_events == 0 else 0.0
        else:
            remaining_pct = float(
                f"{max(0, 100 * (1 - actual_bad_events / allowed_bad_events)):.3f}"
            )

        # Calculate burn rates
        burn_rates = self._calculate_burn_rates(
            sli_name, current_sli, target, remaining_pct
        )

        # Estimate time to exhaustion based on 1h burn rate
        time_to_exhaustion = None
        if burn_rates and burn_rates[0].rate > 1.0 and remaining_pct > 0:
            # hours = remaining_pct / (burn_rate * pct_per_hour)
            # For 28-day window: 100% / (28 * 24) = 0.149% per hour normally
            normal_pct_per_hour = 100.0 / (window_days * 24)
            current_pct_per_hour = normal_pct_per_hour * burn_rates[0].rate
            if current_pct_per_hour > 0:
                time_to_exhaustion = float(
                    f"{remaining_pct / current_pct_per_hour:.1f}"
                )

        return ErrorBudget(
            sli_name=sli_name,
            target=target,
            window_days=window_days,
            total_events=total_events,
            good_events=good_events,
            error_budget_remaining_pct=remaining_pct,
            burn_rates=burn_rates,
            time_to_exhaustion_hours=time_to_exhaustion,
        )

    def _calculate_burn_rates(
        self,
        sli_name: str,
        current_sli: float,
        target: float,
        remaining_pct: float,
    ) -> List[BurnRate]:
        """
        Calculate burn rates for multiple time windows.

        Burn rate = actual error rate / allowed error rate
        - rate = 1.0: consuming budget at expected rate
        - rate > 1.0: consuming faster (bad)
        - rate < 1.0: consuming slower (good)
        """
        burn_rates = []

        for window_hours, threshold in self.BURN_RATE_THRESHOLDS.items():
            # In real implementation, fetch actual metrics from Prometheus
            # For now, estimate based on current SLI
            if current_sli >= target:
                # Meeting SLO, slow/no burn
                rate = 0.0
            else:
                # Estimate burn rate: (target - current) / (target - 0)
                # This is simplified; real implementation would use historical data
                error_rate = 1 - current_sli
                allowed_error_rate = 1 - target
                rate = (
                    error_rate / allowed_error_rate if allowed_error_rate > 0 else 0.0
                )

            alerting = rate > threshold

            burn_rates.append(
                BurnRate(
                    window_hours=window_hours,
                    rate=float(f"{rate:.3f}"),
                    threshold=threshold,
                    alerting=alerting,
                )
            )

        return burn_rates

    def get_status(
        self,
        availability_good: int,
        availability_total: int,
        latency_good: int,
        latency_total: int,
        quality_good: int,
        quality_total: int,
    ) -> SLOStatus:
        """
        Get complete SLO status.

        Args:
            availability_good: Number of successful requests
            availability_total: Total requests
            latency_good: Number of requests < 1s
            latency_total: Total requests
            quality_good: Number of improved queries
            quality_total: Total optimization attempts
        """
        # Calculate error budgets
        availability_budget = self.calculate_error_budget(
            "availability",
            self.AVAILABILITY_TARGET,
            availability_good,
            availability_total,
        )
        latency_budget = self.calculate_error_budget(
            "latency",
            self.LATENCY_TARGET,
            latency_good,
            latency_total,
        )
        quality_budget = self.calculate_error_budget(
            "quality",
            self.QUALITY_TARGET,
            quality_good,
            quality_total,
        )

        error_budgets = {
            "availability": availability_budget,
            "latency": latency_budget,
            "quality": quality_budget,
        }

        # Update Prometheus metrics
        slo_error_budget_remaining.labels(sli="availability").set(
            availability_budget.error_budget_remaining_pct
        )
        slo_error_budget_remaining.labels(sli="latency").set(
            latency_budget.error_budget_remaining_pct
        )
        slo_error_budget_remaining.labels(sli="quality").set(
            quality_budget.error_budget_remaining_pct
        )

        # Determine operating mode and actions
        mode, can_deploy, alerts, recommendations = self._determine_actions(
            error_budgets
        )

        # Calculate overall health (weighted average)
        overall_health = float(
            f"{(availability_budget.error_budget_remaining_pct * 0.5 + latency_budget.error_budget_remaining_pct * 0.3 + quality_budget.error_budget_remaining_pct * 0.2) / 100:.3f}"
        )

        # Update mode metric
        mode_value = {
            ConservativeMode.NORMAL: 0,
            ConservativeMode.CONSERVATIVE: 1,
            ConservativeMode.RESTRICTED: 2,
            ConservativeMode.EMERGENCY: 3,
        }[mode]
        slo_mode.set(mode_value)

        return SLOStatus(
            timestamp=datetime.utcnow(),
            mode=mode,
            error_budgets=error_budgets,
            overall_health=overall_health,
            can_deploy=can_deploy,
            alerts=alerts,
            recommendations=recommendations,
        )

    def _determine_actions(
        self,
        error_budgets: Dict[str, ErrorBudget],
    ) -> Tuple[ConservativeMode, bool, List[str], List[str]]:
        """
        Determine operating mode and required actions based on error budgets.

        Returns: (mode, can_deploy, alerts, recommendations)
        """
        alerts = []
        recommendations = []
        can_deploy = True

        # Find minimum error budget
        min_budget = min(
            b.error_budget_remaining_pct for b in error_budgets.values()
        )

        # Determine mode
        if min_budget <= 0:
            mode = ConservativeMode.EMERGENCY
            can_deploy = False
            alerts.append("EMERGENCY: Error budget exhausted! Activating cache-only mode.")
            recommendations.append("Immediately investigate failures and rollback if needed")
            recommendations.append("Enable cache-only mode to preserve remaining budget")
            self._trigger_emergency_mode()
        elif min_budget < 10:
            mode = ConservativeMode.RESTRICTED
            can_deploy = False
            alerts.append(f"CRITICAL: Error budget at {min_budget:.1f}% - deployments blocked")
            recommendations.append("Page on-call team immediately")
            recommendations.append("Defer non-critical changes until budget recovers")
            self._page_oncall("error_budget_critical", min_budget)
        elif min_budget < 25:
            mode = ConservativeMode.RESTRICTED
            can_deploy = False
            alerts.append(f"WARNING: Error budget at {min_budget:.1f}% - blocking deployments")
            recommendations.append("Review recent changes and error rates")
            recommendations.append("Consider enabling conservative mode")
            slo_deployment_blocked.inc()
        elif min_budget < 50:
            mode = ConservativeMode.CONSERVATIVE
            recommendations.append("Error budget below 50% - enabling conservative mode")
            recommendations.append("Reduce query complexity and increase caching")
        else:
            mode = ConservativeMode.NORMAL

        # Check burn rates
        for sli_name, budget in error_budgets.items():
            for burn_rate in budget.burn_rates:
                if burn_rate.alerting:
                    alerts.append(
                        f"{sli_name}: Fast burn rate {burn_rate.rate:.1f}x "
                        f"in {burn_rate.window_hours}h window (threshold: {burn_rate.threshold}x)"
                    )

        # Check time to exhaustion
        for sli_name, budget in error_budgets.items():
            if budget.time_to_exhaustion_hours and budget.time_to_exhaustion_hours < 4:
                alerts.append(
                    f"{sli_name}: Error budget will exhaust in {budget.time_to_exhaustion_hours:.1f}h"
                )

        self._mode = mode
        self._deployment_blocked = not can_deploy

        return mode, can_deploy, alerts, recommendations

    def _trigger_emergency_mode(self):
        """Activate emergency cache-only mode."""
        logger.critical("EMERGENCY MODE ACTIVATED: Error budget exhausted")
        # In production, this would:
        # 1. Enable cache-only mode (reject all writes)
        # 2. Increase cache TTL
        # 3. Return cached results even if stale
        # 4. Alert on-call team
        # 5. Create incident ticket

    def _page_oncall(self, alert_type: str, value: float):
        """Send page to on-call engineer."""
        # Prevent spam: only page once per hour
        key = f"{alert_type}_{int(time.time() / 3600)}"
        if key in self._last_page_sent:
            return

        logger.critical(f"PAGING ON-CALL: {alert_type} - value: {value:.1f}%")
        self._last_page_sent[key] = time.time()
        # In production, integrate with PagerDuty, Opsgenie, etc.

    def can_deploy(self) -> Tuple[bool, str]:
        """
        Check if deployments are allowed based on error budget.

        Returns: (allowed, reason)
        """
        if self._deployment_blocked:
            return False, f"Deployment blocked: error budget in {self._mode.value} mode"
        return True, "OK"

    def get_budget_report(
        self,
        days: int = 7,
    ) -> Dict:
        """
        Generate error budget report for the past N days.

        In production, this would query Prometheus for historical data.
        """
        return {
            "period_days": days,
            "generated_at": datetime.utcnow().isoformat(),
            "current_mode": self._mode.value,
            "budget_history": [],  # Would contain daily budget snapshots
            "incidents": [],  # Budget exhaustion events
            "deployment_blocks": 0,  # Number of blocked deployments
        }
