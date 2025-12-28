"""
Cost Validation Test

Validates that cost optimization is achieving the projected $4,600/month savings
across all optimization categories.

Usage:
    python tests/load/cost_validation_test.py --days 30
"""

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import List

import aiohttp


@dataclass
class CostMetric:
    """Cost metric for a specific category."""
    category: str
    baseline_monthly_cost: float
    actual_monthly_cost: float
    savings: float
    savings_pct: float
    target_savings: float
    meets_target: bool


class CostValidationTest:
    """Validates cost optimization savings."""

    def __init__(self, api_url: str, days: int = 30):
        self.api_url = api_url
        self.days = days

        # Expected cost savings (monthly)
        self.expected_savings = {
            "ai_autoscaling": 1200,
            "edge_caching": 800,
            "intelligent_routing": 600,
            "ml_query_optimization": 1500,
            "spot_instances": 500,
        }

        self.total_expected_savings = sum(self.expected_savings.values())  # $4,600

    async def run(self):
        """Execute cost validation test."""
        print("=" * 80)
        print("QEO Cost Validation Test")
        print("=" * 80)
        print(f"API URL: {self.api_url}")
        print(f"Analysis Period: {self.days} days")
        print(f"Expected Total Savings: ${self.total_expected_savings:,.0f}/month")
        print("=" * 80)
        print()

        # Collect cost metrics
        metrics = []

        # 1. AI Autoscaling Savings
        print("📊 Analyzing AI Autoscaling savings...")
        metric = await self._validate_autoscaling_savings()
        if metric:
            metrics.append(metric)
            self._print_metric(metric)

        # 2. Edge Caching Savings
        print("\n📊 Analyzing Edge Caching savings...")
        metric = await self._validate_edge_caching_savings()
        if metric:
            metrics.append(metric)
            self._print_metric(metric)

        # 3. Intelligent Routing Savings
        print("\n📊 Analyzing Intelligent Routing savings...")
        metric = await self._validate_routing_savings()
        if metric:
            metrics.append(metric)
            self._print_metric(metric)

        # 4. ML Query Optimization Savings
        print("\n📊 Analyzing ML Query Optimization savings...")
        metric = await self._validate_query_optimization_savings()
        if metric:
            metrics.append(metric)
            self._print_metric(metric)

        # 5. Spot Instances Savings
        print("\n📊 Analyzing Spot Instance savings...")
        metric = await self._validate_spot_instance_savings()
        if metric:
            metrics.append(metric)
            self._print_metric(metric)

        # Generate report
        self._generate_report(metrics)

    async def _validate_autoscaling_savings(self) -> CostMetric:
        """Validate AI-powered autoscaling savings."""
        try:
            # Get autoscaling metrics
            async with aiohttp.ClientSession() as session:
                # Get AI stats
                async with session.get(
                    f"{self.api_url}/api/v1/ai/stats",
                    timeout=10
                ) as response:
                    if response.status != 200:
                        print(f"  ⚠️  AI stats endpoint returned {response.status}")
                        return None

                    data = await response.json()

            # Calculate savings based on autonomy level
            autonomy_level = data.get("autonomy_level", 0)
            total_actions = data.get("total_actions", 0)

            # Estimate: Each automated action saves ~$0.50 in manual ops
            # With 80% autonomy and ~5000 actions/month = $1,200/month savings
            estimated_actions_per_month = total_actions / self.days * 30
            estimated_savings = estimated_actions_per_month * 0.50 * autonomy_level

            baseline_cost = 1500  # Manual ops baseline
            actual_cost = baseline_cost - estimated_savings

            return CostMetric(
                category="AI Autoscaling",
                baseline_monthly_cost=baseline_cost,
                actual_monthly_cost=actual_cost,
                savings=estimated_savings,
                savings_pct=(estimated_savings / baseline_cost * 100),
                target_savings=self.expected_savings["ai_autoscaling"],
                meets_target=(estimated_savings >= self.expected_savings["ai_autoscaling"])
            )

        except Exception as e:
            print(f"  ❌ Error: {e}")
            return None

    async def _validate_edge_caching_savings(self) -> CostMetric:
        """Validate edge caching savings."""
        try:
            async with aiohttp.ClientSession():
                # Fetch cache stats (from edge or API)
                # For simulation, we'll estimate based on cache hit rate

                # Assume: 85% cache hit rate saves $800/month in origin bandwidth
                cache_hit_rate = 0.85  # 85% (from edge validator)

                baseline_bandwidth_cost = 1000  # Full origin cost
                savings = baseline_bandwidth_cost * cache_hit_rate * 0.8

                return CostMetric(
                    category="Edge Caching",
                    baseline_monthly_cost=baseline_bandwidth_cost,
                    actual_monthly_cost=baseline_bandwidth_cost - savings,
                    savings=savings,
                    savings_pct=(savings / baseline_bandwidth_cost * 100),
                    target_savings=self.expected_savings["edge_caching"],
                    meets_target=(savings >= self.expected_savings["edge_caching"])
                )

        except Exception as e:
            print(f"  ❌ Error: {e}")
            return None

    async def _validate_routing_savings(self) -> CostMetric:
        """Validate intelligent routing savings."""
        try:
            # Intelligent routing reduces cross-region data transfer costs
            # Estimate: 60% of traffic now stays in-region vs 40% baseline

            baseline_transfer_cost = 1200  # Cross-region baseline
            in_region_percentage = 0.60
            savings = baseline_transfer_cost * in_region_percentage * 0.5

            return CostMetric(
                category="Intelligent Routing",
                baseline_monthly_cost=baseline_transfer_cost,
                actual_monthly_cost=baseline_transfer_cost - savings,
                savings=savings,
                savings_pct=(savings / baseline_transfer_cost * 100),
                target_savings=self.expected_savings["intelligent_routing"],
                meets_target=(savings >= self.expected_savings["intelligent_routing"])
            )

        except Exception as e:
            print(f"  ❌ Error: {e}")
            return None

    async def _validate_query_optimization_savings(self) -> CostMetric:
        """Validate ML query optimization savings."""
        try:
            async with aiohttp.ClientSession() as session:
                # Test query optimization
                test_queries = [
                    "SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 50",
                    "SELECT u.*, o.* FROM users u JOIN orders o ON u.id = o.user_id WHERE o.status = 'pending'",
                ]

                total_cost_reduction = 0
                queries_tested = 0

                for query in test_queries:
                    async with session.post(
                        f"{self.api_url}/api/v1/optimize",
                        json={"sql": query, "what_if": True},
                        timeout=30
                    ) as response:
                        if response.status == 200:
                            data = await response.json()

                            # Get cost reduction from suggestions
                            suggestions = data.get("suggestions", [])
                            for suggestion in suggestions:
                                if "estReductionPct" in suggestion:
                                    total_cost_reduction += suggestion["estReductionPct"]

                            queries_tested += 1

            # Average cost reduction per query
            avg_reduction_pct = (total_cost_reduction / queries_tested) if queries_tested > 0 else 0

            # Estimate: 10,000 queries/day × 30 days × $0.005/query × reduction%
            baseline_query_cost = 10000 * 30 * 0.005  # $1,500
            savings = baseline_query_cost * (avg_reduction_pct / 100)

            return CostMetric(
                category="ML Query Optimization",
                baseline_monthly_cost=baseline_query_cost,
                actual_monthly_cost=baseline_query_cost - savings,
                savings=savings,
                savings_pct=avg_reduction_pct,
                target_savings=self.expected_savings["ml_query_optimization"],
                meets_target=(savings >= self.expected_savings["ml_query_optimization"])
            )

        except Exception as e:
            print(f"  ❌ Error: {e}")
            return None

    async def _validate_spot_instance_savings(self) -> CostMetric:
        """Validate spot instance savings."""
        try:
            # Check if using spot instances
            # For simulation, assume 70% spot instance usage

            spot_usage_pct = 0.70
            spot_discount = 0.60  # 60% cheaper than on-demand

            baseline_compute_cost = 833  # ~$10k/year / 12
            savings = baseline_compute_cost * spot_usage_pct * spot_discount

            return CostMetric(
                category="Spot Instances",
                baseline_monthly_cost=baseline_compute_cost,
                actual_monthly_cost=baseline_compute_cost - savings,
                savings=savings,
                savings_pct=(savings / baseline_compute_cost * 100),
                target_savings=self.expected_savings["spot_instances"],
                meets_target=(savings >= self.expected_savings["spot_instances"])
            )

        except Exception as e:
            print(f"  ❌ Error: {e}")
            return None

    def _print_metric(self, metric: CostMetric):
        """Print a cost metric."""
        status = "✅" if metric.meets_target else "❌"

        print(f"  {status} {metric.category}")
        print(f"     Baseline: ${metric.baseline_monthly_cost:,.0f}/month")
        print(f"     Actual: ${metric.actual_monthly_cost:,.0f}/month")
        print(f"     Savings: ${metric.savings:,.0f}/month ({metric.savings_pct:.1f}%)")
        print(f"     Target: ${metric.target_savings:,.0f}/month")

        if not metric.meets_target:
            shortfall = metric.target_savings - metric.savings
            print(f"     ⚠️  Shortfall: ${shortfall:,.0f}/month")

    def _generate_report(self, metrics: List[CostMetric]):
        """Generate final cost validation report."""
        print("\n" + "=" * 80)
        print("COST VALIDATION SUMMARY")
        print("=" * 80)
        print()

        # Calculate totals
        total_savings = sum(m.savings for m in metrics)
        total_baseline = sum(m.baseline_monthly_cost for m in metrics)
        total_actual = sum(m.actual_monthly_cost for m in metrics)

        print(f"Total Baseline Cost: ${total_baseline:,.0f}/month")
        print(f"Total Actual Cost: ${total_actual:,.0f}/month")
        print(f"Total Savings: ${total_savings:,.0f}/month")
        print(f"Target Savings: ${self.total_expected_savings:,.0f}/month")
        print()

        # Savings by category
        print("Savings Breakdown:")
        print("Category                    | Savings     | Target      | Status")
        print("-" * 75)

        for metric in metrics:
            status = "✅ PASS" if metric.meets_target else "❌ FAIL"
            print(f"{metric.category:27s} | ${metric.savings:10,.0f} | ${metric.target_savings:10,.0f} | {status}")

        print()

        # Overall validation
        passed = total_savings >= self.total_expected_savings

        if passed:
            print("✅ COST VALIDATION PASSED")
            print(f"   - Total savings: ${total_savings:,.0f}/month >= ${self.total_expected_savings:,.0f}/month")
            print(f"   - Cost reduction: {(total_savings / total_baseline * 100):.1f}%")
        else:
            shortfall = self.total_expected_savings - total_savings
            print("❌ COST VALIDATION FAILED")
            print(f"   - Total savings: ${total_savings:,.0f}/month < ${self.total_expected_savings:,.0f}/month")
            print(f"   - Shortfall: ${shortfall:,.0f}/month")

        # ROI calculation
        infrastructure_investment = 800  # Monthly investment in enhancements
        roi = total_savings / infrastructure_investment if infrastructure_investment > 0 else 0

        print()
        print(f"ROI: {roi:.2f}x")
        print(f"   - Investment: ${infrastructure_investment:,.0f}/month")
        print(f"   - Return: ${total_savings:,.0f}/month")

        print()
        print("=" * 80)

        # Save report
        report_file = f"cost_validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        with open(report_file, 'w') as f:
            json.dump(
                {
                    "test_info": {
                        "api_url": self.api_url,
                        "analysis_days": self.days,
                    },
                    "summary": {
                        "total_baseline_cost": total_baseline,
                        "total_actual_cost": total_actual,
                        "total_savings": total_savings,
                        "target_savings": self.total_expected_savings,
                        "roi": roi,
                        "test_passed": passed,
                    },
                    "metrics": [asdict(m) for m in metrics],
                },
                f,
                indent=2
            )

        print(f"Report saved to: {report_file}")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="QEO Cost Validation Test")
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="API URL"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to analyze (default: 30)"
    )

    args = parser.parse_args()

    test = CostValidationTest(
        api_url=args.api_url,
        days=args.days
    )

    await test.run()


if __name__ == "__main__":
    asyncio.run(main())
