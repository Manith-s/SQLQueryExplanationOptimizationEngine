"""
Cost optimization and tracking system.

Features:
- Track costs per query (CPU, memory, database)
- Cloud provider billing integration (AWS, GCP, Azure)
- Cost-aware autoscaling
- FinOps recommendations
- Query cost limits
"""

from .analyzer import (
    CostAnalyzer,
    CostRecommendation,
    CostTrend,
    QueryCost,
)

__all__ = [
    "CostAnalyzer",
    "QueryCost",
    "CostRecommendation",
    "CostTrend",
]
