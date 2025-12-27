"""
SLO (Service Level Objective) Management System.

Tracks SLIs (Service Level Indicators), calculates error budgets,
monitors burn rates, and triggers automated responses.
"""

from .manager import (
    SLOManager,
    SLOStatus,
    ErrorBudget,
    BurnRate,
    ConservativeMode,
)

__all__ = [
    "SLOManager",
    "SLOStatus",
    "ErrorBudget",
    "BurnRate",
    "ConservativeMode",
]
