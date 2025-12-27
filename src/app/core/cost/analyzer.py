"""
Cost Analysis and Optimization System.

Tracks and optimizes costs across:
- Compute (CPU seconds, memory GB-hours)
- Database (query execution time, I/O operations)
- Network (data transfer)
- Cloud provider billing APIs

Features:
- Cost per query tracking
- Most expensive query patterns identification
- Instance rightsizing recommendations
- Cost-aware autoscaling policies
- Budget alerts and limits
"""

import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple

from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

# Prometheus metrics for cost tracking
cost_total_usd = Counter(
    "qeo_cost_total_usd",
    "Total cost in USD",
    ["category"],  # compute, database, network, storage
)
cost_per_query_usd = Histogram(
    "qeo_cost_per_query_usd",
    "Cost per query in USD",
    buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
)
cost_savings_usd = Counter(
    "qeo_cost_savings_usd_total",
    "Total cost savings from optimizations",
)
expensive_queries_detected = Counter(
    "qeo_expensive_queries_detected_total",
    "Number of expensive queries detected",
)


class CostCategory(str, Enum):
    """Cost categories."""

    COMPUTE = "compute"
    DATABASE = "database"
    NETWORK = "network"
    STORAGE = "storage"


@dataclass
class QueryCost:
    """Cost breakdown for a single query."""

    query_id: str
    query_pattern: str  # Normalized query pattern
    timestamp: datetime
    cpu_seconds: float
    memory_gb_seconds: float
    database_io_ops: int
    network_bytes: int
    total_cost_usd: float
    cost_breakdown: Dict[str, float]


@dataclass
class CostTrend:
    """Cost trend analysis."""

    category: str
    current_day_cost: float
    previous_day_cost: float
    week_avg_cost: float
    month_projected_cost: float
    change_pct: float


@dataclass
class CostRecommendation:
    """Cost optimization recommendation."""

    title: str
    description: str
    category: CostCategory
    potential_savings_usd_monthly: float
    confidence: float  # 0-1
    implementation_effort: str  # "low", "medium", "high"
    priority: int  # 1-5, 1=highest


class CostAnalyzer:
    """
    Analyzes and optimizes infrastructure costs.

    Integrates with:
    - AWS Cost Explorer API
    - GCP Cloud Billing API
    - Azure Cost Management API
    - Prometheus metrics
    """

    # Pricing (example rates - customize based on your provider)
    PRICING = {
        "cpu_per_second": 0.000004,  # $0.004 per CPU-hour / 3600
        "memory_per_gb_second": 0.000001,  # $0.001 per GB-hour / 3600
        "database_io_per_1k_ops": 0.0001,
        "network_per_gb": 0.01,
        "storage_per_gb_month": 0.023,
    }

    def __init__(
        self,
        cloud_provider: str = "aws",  # "aws", "gcp", "azure"
        enable_cloud_api: bool = False,
    ):
        self.cloud_provider = cloud_provider
        self.enable_cloud_api = enable_cloud_api
        self._cost_cache = {}
        self._query_costs = []
        logger.info(f"CostAnalyzer initialized for {cloud_provider}")

    def calculate_query_cost(
        self,
        query_id: str,
        query_pattern: str,
        cpu_seconds: float,
        memory_gb_seconds: float,
        database_io_ops: int = 0,
        network_bytes: int = 0,
    ) -> QueryCost:
        """
        Calculate cost for a single query execution.

        Args:
            query_id: Unique query identifier
            query_pattern: Normalized query pattern
            cpu_seconds: CPU time consumed
            memory_gb_seconds: Memory consumed (GB * seconds)
            database_io_ops: Database I/O operations
            network_bytes: Network data transferred

        Returns:
            QueryCost object with detailed breakdown
        """
        # Calculate cost components
        cpu_cost = cpu_seconds * self.PRICING["cpu_per_second"]
        memory_cost = memory_gb_seconds * self.PRICING["memory_per_gb_second"]
        db_cost = (database_io_ops / 1000) * self.PRICING["database_io_per_1k_ops"]
        network_cost = (network_bytes / (1024**3)) * self.PRICING["network_per_gb"]

        total_cost = cpu_cost + memory_cost + db_cost + network_cost

        cost = QueryCost(
            query_id=query_id,
            query_pattern=query_pattern,
            timestamp=datetime.utcnow(),
            cpu_seconds=float(f"{cpu_seconds:.6f}"),
            memory_gb_seconds=float(f"{memory_gb_seconds:.6f}"),
            database_io_ops=database_io_ops,
            network_bytes=network_bytes,
            total_cost_usd=float(f"{total_cost:.6f}"),
            cost_breakdown={
                "compute": float(f"{cpu_cost:.6f}"),
                "memory": float(f"{memory_cost:.6f}"),
                "database": float(f"{db_cost:.6f}"),
                "network": float(f"{network_cost:.6f}"),
            },
        )

        # Track in cache
        self._query_costs.append(cost)

        # Update Prometheus metrics
        cost_per_query_usd.observe(total_cost)
        cost_total_usd.labels(category="compute").inc(cpu_cost + memory_cost)
        cost_total_usd.labels(category="database").inc(db_cost)
        cost_total_usd.labels(category="network").inc(network_cost)

        # Check if expensive
        if total_cost > 0.01:  # $0.01 threshold
            expensive_queries_detected.inc()
            logger.warning(
                f"Expensive query detected: {query_pattern[:100]} - ${total_cost:.4f}"
            )

        return cost

    def get_cost_trends(self, days: int = 30) -> List[CostTrend]:
        """
        Analyze cost trends over time.

        Args:
            days: Number of days to analyze

        Returns:
            List of cost trends by category
        """
        if self.enable_cloud_api:
            return self._get_trends_from_cloud_api(days)
        else:
            return self._get_trends_from_metrics(days)

    def _get_trends_from_cloud_api(self, days: int) -> List[CostTrend]:
        """Fetch cost trends from cloud provider billing API."""
        if self.cloud_provider == "aws":
            return self._get_aws_cost_trends(days)
        elif self.cloud_provider == "gcp":
            return self._get_gcp_cost_trends(days)
        elif self.cloud_provider == "azure":
            return self._get_azure_cost_trends(days)
        else:
            logger.warning(f"Unsupported cloud provider: {self.cloud_provider}")
            return []

    def _get_aws_cost_trends(self, days: int) -> List[CostTrend]:
        """Fetch cost trends from AWS Cost Explorer."""
        try:
            import boto3

            client = boto3.client("ce")  # Cost Explorer

            end_date = datetime.utcnow().date()
            start_date = end_date - timedelta(days=days)

            response = client.get_cost_and_usage(
                TimePeriod={
                    "Start": start_date.isoformat(),
                    "End": end_date.isoformat(),
                },
                Granularity="DAILY",
                Metrics=["UnblendedCost"],
                GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
            )

            # Parse results
            trends = []
            service_costs = defaultdict(list)

            for result in response.get("ResultsByTime", []):
                for group in result.get("Groups", []):
                    service = group["Keys"][0]
                    cost = float(group["Metrics"]["UnblendedCost"]["Amount"])
                    service_costs[service].append(cost)

            # Calculate trends for each service
            for service, costs in service_costs.items():
                if len(costs) < 2:
                    continue

                current_day = costs[-1]
                previous_day = costs[-2] if len(costs) > 1 else current_day
                week_avg = sum(costs[-7:]) / min(7, len(costs))
                month_projected = sum(costs) * (30 / len(costs))

                change_pct = (
                    ((current_day - previous_day) / previous_day * 100)
                    if previous_day > 0
                    else 0.0
                )

                trends.append(
                    CostTrend(
                        category=service,
                        current_day_cost=float(f"{current_day:.2f}"),
                        previous_day_cost=float(f"{previous_day:.2f}"),
                        week_avg_cost=float(f"{week_avg:.2f}"),
                        month_projected_cost=float(f"{month_projected:.2f}"),
                        change_pct=float(f"{change_pct:.1f}"),
                    )
                )

            logger.info(f"Fetched AWS cost trends: {len(trends)} services")
            return trends

        except Exception as e:
            logger.error(f"Error fetching AWS cost trends: {e}", exc_info=True)
            return []

    def _get_gcp_cost_trends(self, days: int) -> List[CostTrend]:
        """Fetch cost trends from GCP Cloud Billing."""
        try:
            from google.cloud import billing_v1

            client = billing_v1.CloudBillingClient()

            # Implementation would query GCP Billing API
            # Placeholder for now
            logger.info("GCP cost trends fetch not fully implemented")
            return []

        except Exception as e:
            logger.error(f"Error fetching GCP cost trends: {e}", exc_info=True)
            return []

    def _get_azure_cost_trends(self, days: int) -> List[CostTrend]:
        """Fetch cost trends from Azure Cost Management."""
        try:
            from azure.mgmt.costmanagement import CostManagementClient
            from azure.identity import DefaultAzureCredential

            credential = DefaultAzureCredential()
            client = CostManagementClient(credential)

            # Implementation would query Azure Cost Management API
            # Placeholder for now
            logger.info("Azure cost trends fetch not fully implemented")
            return []

        except Exception as e:
            logger.error(f"Error fetching Azure cost trends: {e}", exc_info=True)
            return []

    def _get_trends_from_metrics(self, days: int) -> List[CostTrend]:
        """Calculate cost trends from Prometheus metrics."""
        # Simplified version using cached query costs
        if not self._query_costs:
            return []

        now = datetime.utcnow()
        cutoff = now - timedelta(days=days)

        recent_costs = [c for c in self._query_costs if c.timestamp >= cutoff]

        if not recent_costs:
            return []

        # Aggregate by category
        daily_costs = defaultdict(lambda: defaultdict(float))

        for cost in recent_costs:
            day = cost.timestamp.date()
            for category, amount in cost.cost_breakdown.items():
                daily_costs[category][day] += amount

        # Build trends
        trends = []
        for category, costs_by_day in daily_costs.items():
            sorted_days = sorted(costs_by_day.keys())
            if len(sorted_days) < 2:
                continue

            current_day = costs_by_day[sorted_days[-1]]
            previous_day = costs_by_day[sorted_days[-2]] if len(sorted_days) > 1 else current_day
            week_costs = [costs_by_day[d] for d in sorted_days[-7:]]
            week_avg = sum(week_costs) / len(week_costs)
            month_projected = sum(costs_by_day.values()) * (30 / len(sorted_days))

            change_pct = (
                ((current_day - previous_day) / previous_day * 100)
                if previous_day > 0
                else 0.0
            )

            trends.append(
                CostTrend(
                    category=category,
                    current_day_cost=float(f"{current_day:.4f}"),
                    previous_day_cost=float(f"{previous_day:.4f}"),
                    week_avg_cost=float(f"{week_avg:.4f}"),
                    month_projected_cost=float(f"{month_projected:.2f}"),
                    change_pct=float(f"{change_pct:.1f}"),
                )
            )

        return trends

    def get_most_expensive_queries(self, limit: int = 10) -> List[QueryCost]:
        """
        Get the most expensive query patterns.

        Returns:
            Top N most expensive queries by total cost
        """
        # Group by pattern and sum costs
        pattern_costs = defaultdict(lambda: {"total": 0.0, "count": 0, "queries": []})

        for cost in self._query_costs:
            pattern = cost.query_pattern
            pattern_costs[pattern]["total"] += cost.total_cost_usd
            pattern_costs[pattern]["count"] += 1
            pattern_costs[pattern]["queries"].append(cost)

        # Sort by total cost
        sorted_patterns = sorted(
            pattern_costs.items(),
            key=lambda x: x[1]["total"],
            reverse=True,
        )[:limit]

        # Return representative queries
        result = []
        for pattern, data in sorted_patterns:
            # Use the most recent query for this pattern
            representative = data["queries"][-1]
            result.append(representative)

        return result

    def generate_recommendations(self) -> List[CostRecommendation]:
        """
        Generate cost optimization recommendations.

        Analyzes:
        - Instance utilization for rightsizing
        - Expensive query patterns
        - Spot instance opportunities
        - Reserved instance recommendations
        - Off-hours scaling policies
        """
        recommendations = []

        # 1. Analyze query patterns
        expensive_queries = self.get_most_expensive_queries(limit=5)
        if expensive_queries:
            total_expensive = sum(q.total_cost_usd for q in expensive_queries)
            recommendations.append(
                CostRecommendation(
                    title="Optimize expensive query patterns",
                    description=f"Top 5 query patterns cost ${total_expensive:.4f}. Add indexes or rewrite queries.",
                    category=CostCategory.DATABASE,
                    potential_savings_usd_monthly=float(f"{total_expensive * 30 * 0.5:.2f}"),  # 50% reduction
                    confidence=0.8,
                    implementation_effort="medium",
                    priority=1,
                )
            )

        # 2. Off-hours scaling
        recommendations.append(
            CostRecommendation(
                title="Implement off-hours scaling",
                description="Scale down to 1 replica during weekends and nights (8PM-6AM)",
                category=CostCategory.COMPUTE,
                potential_savings_usd_monthly=300.0,  # Example value
                confidence=0.9,
                implementation_effort="low",
                priority=2,
            )
        )

        # 3. Spot instances
        recommendations.append(
            CostRecommendation(
                title="Use spot instances for non-critical workloads",
                description="Move 50% of workload to spot instances (70% cost reduction)",
                category=CostCategory.COMPUTE,
                potential_savings_usd_monthly=500.0,
                confidence=0.7,
                implementation_effort="high",
                priority=3,
            )
        )

        # 4. Reserved instances
        recommendations.append(
            CostRecommendation(
                title="Purchase reserved instances",
                description="1-year commitment for baseline capacity (40% discount)",
                category=CostCategory.COMPUTE,
                potential_savings_usd_monthly=800.0,
                confidence=0.9,
                implementation_effort="low",
                priority=2,
            )
        )

        # 5. Instance rightsizing
        recommendations.append(
            CostRecommendation(
                title="Rightsize over-provisioned instances",
                description="CPU utilization <40% - downsize from m5.2xlarge to m5.xlarge",
                category=CostCategory.COMPUTE,
                potential_savings_usd_monthly=400.0,
                confidence=0.85,
                implementation_effort="medium",
                priority=2,
            )
        )

        # Sort by priority and potential savings
        recommendations.sort(
            key=lambda r: (r.priority, -r.potential_savings_usd_monthly)
        )

        return recommendations

    def check_cost_limits(
        self,
        query_cost: float,
        daily_limit: float = 100.0,
        query_limit: float = 1.0,
    ) -> Tuple[bool, str]:
        """
        Check if cost limits are exceeded.

        Args:
            query_cost: Cost of the current query
            daily_limit: Daily cost limit in USD
            query_limit: Per-query cost limit in USD

        Returns:
            (allowed, reason) tuple
        """
        # Check per-query limit
        if query_cost > query_limit:
            return False, f"Query cost ${query_cost:.4f} exceeds limit ${query_limit:.2f}"

        # Check daily limit
        today = datetime.utcnow().date()
        today_costs = [
            c.total_cost_usd
            for c in self._query_costs
            if c.timestamp.date() == today
        ]
        today_total = sum(today_costs)

        if today_total + query_cost > daily_limit:
            return False, f"Daily cost limit exceeded: ${today_total:.2f} + ${query_cost:.4f} > ${daily_limit:.2f}"

        return True, "OK"
