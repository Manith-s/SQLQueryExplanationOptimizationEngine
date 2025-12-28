"""
SLO Data Models

Defines data structures for Service Level Indicators (SLIs),
Service Level Objectives (SLOs), and Error Budgets.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional


class SLIType(Enum):
    """Types of Service Level Indicators"""

    AVAILABILITY = "availability"
    LATENCY = "latency"
    QUALITY = "quality"


class SLOMode(Enum):
    """SLO operating modes based on error budget"""

    NORMAL = "normal"  # Budget > 50%
    CONSERVATIVE = "conservative"  # Budget 25-50%
    RESTRICTED = "restricted"  # Budget 10-25%
    EMERGENCY = "emergency"  # Budget < 10%
    EXHAUSTED = "exhausted"  # Budget = 0%


@dataclass
class SLI:
    """Service Level Indicator definition and measurement"""

    name: str
    type: SLIType
    description: str
    target: float  # Target value (e.g., 0.999 for 99.9% availability)
    measurement_window: timedelta = field(default_factory=lambda: timedelta(days=28))

    # Current measurements
    good_events: int = 0
    total_events: int = 0
    current_value: float = 0.0
    last_updated: Optional[datetime] = None

    def calculate(self) -> float:
        """Calculate current SLI value"""
        if self.total_events == 0:
            return 1.0

        self.current_value = float(f"{self.good_events / self.total_events:.6f}")
        self.last_updated = datetime.utcnow()
        return self.current_value

    def is_meeting_target(self) -> bool:
        """Check if SLI is meeting target"""
        return self.current_value >= self.target

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "type": self.type.value,
            "description": self.description,
            "target": self.target,
            "current_value": self.current_value,
            "good_events": self.good_events,
            "total_events": self.total_events,
            "is_meeting_target": self.is_meeting_target(),
            "last_updated": (
                self.last_updated.isoformat() if self.last_updated else None
            ),
        }


@dataclass
class BurnRate:
    """Error budget burn rate for a specific time window"""

    window: timedelta
    rate: float  # Actual burn rate
    threshold: float  # Alert threshold
    is_alerting: bool = False

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "window_hours": self.window.total_seconds() / 3600,
            "rate": round(self.rate, 3),
            "threshold": self.threshold,
            "is_alerting": self.is_alerting,
        }


@dataclass
class ErrorBudget:
    """Error budget tracking for an SLO"""

    slo_name: str
    target: float  # SLO target (e.g., 0.999)
    window_days: int = 28  # Measurement window

    # Budget tracking
    total_budget: float = 0.0  # Total allowed error budget (1 - target)
    consumed: float = 0.0  # Budget consumed so far
    remaining: float = 0.0  # Budget remaining
    remaining_percentage: float = 100.0

    # Burn rate tracking
    burn_rates: List[BurnRate] = field(default_factory=list)

    # Time tracking
    time_to_exhaustion: Optional[timedelta] = None
    last_calculated: Optional[datetime] = None

    def calculate(self, current_sli_value: float) -> None:
        """Calculate error budget consumption"""
        # Total budget = 1 - target (e.g., 1 - 0.999 = 0.001 = 0.1%)
        self.total_budget = 1.0 - self.target

        # Consumed = how much we've deviated from target
        error_rate = 1.0 - current_sli_value
        self.consumed = error_rate

        # Remaining = total budget - consumed
        self.remaining = max(0.0, self.total_budget - self.consumed)

        # Percentage remaining
        if self.total_budget > 0:
            self.remaining_percentage = (self.remaining / self.total_budget) * 100
        else:
            self.remaining_percentage = 100.0

        self.last_calculated = datetime.utcnow()

    def get_mode(self) -> SLOMode:
        """Determine current SLO mode based on budget"""
        if self.remaining_percentage <= 0:
            return SLOMode.EXHAUSTED
        elif self.remaining_percentage < 10:
            return SLOMode.EMERGENCY
        elif self.remaining_percentage < 25:
            return SLOMode.RESTRICTED
        elif self.remaining_percentage < 50:
            return SLOMode.CONSERVATIVE
        else:
            return SLOMode.NORMAL

    def estimate_time_to_exhaustion(self, burn_rate_1h: float) -> Optional[timedelta]:
        """Estimate time until budget is exhausted at current burn rate"""
        if burn_rate_1h <= 0 or self.remaining <= 0:
            return None

        # Time to exhaustion = remaining budget / burn rate
        hours_remaining = self.remaining / (burn_rate_1h / 3600)  # Convert to hours
        self.time_to_exhaustion = timedelta(hours=hours_remaining)
        return self.time_to_exhaustion

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "slo_name": self.slo_name,
            "target": self.target,
            "window_days": self.window_days,
            "total_budget": round(self.total_budget, 6),
            "consumed": round(self.consumed, 6),
            "remaining": round(self.remaining, 6),
            "remaining_percentage": round(self.remaining_percentage, 2),
            "mode": self.get_mode().value,
            "burn_rates": [br.to_dict() for br in self.burn_rates],
            "time_to_exhaustion_hours": (
                round(self.time_to_exhaustion.total_seconds() / 3600, 1)
                if self.time_to_exhaustion
                else None
            ),
            "last_calculated": (
                self.last_calculated.isoformat() if self.last_calculated else None
            ),
        }


@dataclass
class SLO:
    """Service Level Objective definition"""

    name: str
    description: str
    sli: SLI
    target: float  # Target value (e.g., 0.999 for 99.9%)
    window_days: int = 28

    # Error budget
    error_budget: Optional[ErrorBudget] = None

    # Status
    is_meeting: bool = True
    last_breach: Optional[datetime] = None
    breaches_in_window: int = 0

    def __post_init__(self):
        """Initialize error budget"""
        if self.error_budget is None:
            self.error_budget = ErrorBudget(
                slo_name=self.name, target=self.target, window_days=self.window_days
            )

    def evaluate(self) -> bool:
        """Evaluate if SLO is being met"""
        # Calculate SLI
        sli_value = self.sli.calculate()

        # Update error budget
        self.error_budget.calculate(sli_value)

        # Check if meeting target
        self.is_meeting = sli_value >= self.target

        if not self.is_meeting:
            self.last_breach = datetime.utcnow()
            self.breaches_in_window += 1

        return self.is_meeting

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "description": self.description,
            "target": self.target,
            "window_days": self.window_days,
            "sli": self.sli.to_dict(),
            "error_budget": self.error_budget.to_dict() if self.error_budget else None,
            "is_meeting": self.is_meeting,
            "last_breach": self.last_breach.isoformat() if self.last_breach else None,
            "breaches_in_window": self.breaches_in_window,
        }


@dataclass
class SLOStatus:
    """Overall SLO status for the system"""

    timestamp: datetime
    slos: List[SLO]
    overall_mode: SLOMode
    active_restrictions: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "overall_mode": self.overall_mode.value,
            "slos": [slo.to_dict() for slo in self.slos],
            "active_restrictions": self.active_restrictions,
            "recommendations": self.recommendations,
            "summary": {
                "total_slos": len(self.slos),
                "meeting_slos": sum(1 for slo in self.slos if slo.is_meeting),
                "breaching_slos": sum(1 for slo in self.slos if not slo.is_meeting),
            },
        }
