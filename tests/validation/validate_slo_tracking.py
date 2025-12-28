"""
SLO Tracking Validation Suite.

Verifies SLO calculations, error budgets, and burn rate monitoring.

Usage:
    python tests/validation/validate_slo_tracking.py
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple

import requests

# API endpoint
API_URL = "http://localhost:8000"

# SLO Targets (from slo/manager.py)
AVAILABILITY_TARGET = 0.995  # 99.5%
LATENCY_TARGET = 0.99  # 99%
QUALITY_TARGET = 0.90  # 90%
WINDOW_DAYS = 28

# Burn rate thresholds
BURN_RATE_THRESHOLDS = {
    1: 14.4,  # 1h window
    6: 6.0,  # 6h window
    24: 3.0,  # 24h window
    72: 1.5,  # 72h window
}


@dataclass
class ValidationResult:
    """Result of a validation test."""

    test_name: str
    passed: bool
    message: str
    duration_ms: float
    details: Dict = None


class SLOTrackingValidator:
    """Validates SLO tracking system."""

    def __init__(self):
        self.results: List[ValidationResult] = []

    async def validate_all(self) -> Tuple[bool, List[ValidationResult]]:
        """Run all SLO validation tests."""
        print("=" * 80)
        print("QEO SLO Tracking Validation Suite")
        print("=" * 80)
        print()

        # Run all tests
        await self.test_slo_api_endpoints()
        await self.test_error_budget_calculation()
        await self.test_burn_rate_calculation()
        await self.test_sli_recording()
        await self.test_deployment_gating()
        await self.test_slo_report_generation()

        # Summary
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        success = all(r.passed for r in self.results)

        print()
        print("=" * 80)
        print(f"Validation Summary: {passed}/{total} tests passed")
        print("=" * 80)
        print()

        for result in self.results:
            status = "✓ PASS" if result.passed else "✗ FAIL"
            print(f"{status} - {result.test_name} ({result.duration_ms:.0f}ms)")
            if not result.passed:
                print(f"      {result.message}")

        return success, self.results

    async def test_slo_api_endpoints(self):
        """Test all SLO API endpoints are accessible."""
        print("Testing SLO API endpoints...")

        endpoints = [
            "/api/v1/slo/status",
            "/api/v1/slo/budget",
            "/api/v1/slo/report",
            "/api/v1/slo/can-deploy",
        ]

        for endpoint in endpoints:
            start = time.time()
            try:
                response = requests.get(
                    f"{API_URL}{endpoint}",
                    timeout=5,
                )
                duration_ms = (time.time() - start) * 1000

                if response.status_code == 200:
                    data = response.json()

                    self.results.append(
                        ValidationResult(
                            test_name=f"SLO API - {endpoint}",
                            passed=True,
                            message="Endpoint accessible",
                            duration_ms=duration_ms,
                            details=data,
                        )
                    )
                    print(f"  ✓ {endpoint}: OK")
                else:
                    self.results.append(
                        ValidationResult(
                            test_name=f"SLO API - {endpoint}",
                            passed=False,
                            message=f"HTTP {response.status_code}",
                            duration_ms=duration_ms,
                        )
                    )
                    print(f"  ✗ {endpoint}: HTTP {response.status_code}")

            except Exception as e:
                duration_ms = (time.time() - start) * 1000
                self.results.append(
                    ValidationResult(
                        test_name=f"SLO API - {endpoint}",
                        passed=False,
                        message=str(e),
                        duration_ms=duration_ms,
                    )
                )
                print(f"  ✗ {endpoint}: {e}")

    async def test_error_budget_calculation(self):
        """Verify error budget calculations are correct."""
        print("\nTesting error budget calculations...")

        start = time.time()
        try:
            response = requests.get(
                f"{API_URL}/api/v1/slo/budget",
                timeout=5,
            )
            duration_ms = (time.time() - start) * 1000

            if response.status_code == 200:
                data = response.json()

                # Verify structure
                required_fields = ["availability", "latency", "quality"]
                has_all_fields = all(field in data for field in required_fields)

                if not has_all_fields:
                    self.results.append(
                        ValidationResult(
                            test_name="Error Budget Calculation",
                            passed=False,
                            message="Missing required SLI fields",
                            duration_ms=duration_ms,
                        )
                    )
                    print("  ✗ Missing fields in error budget response")
                    return

                # Verify each SLI
                for sli_name, sli_data in data.items():
                    if sli_name not in required_fields:
                        continue

                    # Check required fields
                    required_sli_fields = [
                        "remaining_pct",
                        "consumed_pct",
                        "budget_minutes",
                    ]
                    has_sli_fields = all(
                        field in sli_data for field in required_sli_fields
                    )

                    if not has_sli_fields:
                        self.results.append(
                            ValidationResult(
                                test_name=f"Error Budget - {sli_name}",
                                passed=False,
                                message=f"Missing fields in {sli_name}",
                                duration_ms=duration_ms,
                            )
                        )
                        print(f"  ✗ {sli_name}: Missing required fields")
                        continue

                    # Verify budget math: remaining + consumed = 100%
                    remaining = sli_data["remaining_pct"]
                    consumed = sli_data["consumed_pct"]
                    total = remaining + consumed

                    budget_valid = abs(total - 100.0) < 0.01  # Allow small float error

                    # Verify remaining is between 0-100
                    range_valid = 0 <= remaining <= 100

                    passed = budget_valid and range_valid

                    self.results.append(
                        ValidationResult(
                            test_name=f"Error Budget - {sli_name}",
                            passed=passed,
                            message=f"Remaining: {remaining:.1f}%, Consumed: {consumed:.1f}%",
                            duration_ms=duration_ms,
                            details={
                                "remaining_pct": remaining,
                                "consumed_pct": consumed,
                                "budget_minutes": sli_data.get("budget_minutes", 0),
                            },
                        )
                    )

                    if passed:
                        print(f"  ✓ {sli_name}: {remaining:.1f}% remaining")
                    else:
                        print(f"  ✗ {sli_name}: Budget math error (total={total:.1f}%)")

            else:
                self.results.append(
                    ValidationResult(
                        test_name="Error Budget Calculation",
                        passed=False,
                        message=f"HTTP {response.status_code}",
                        duration_ms=duration_ms,
                    )
                )
                print(f"  ✗ Budget API returned HTTP {response.status_code}")

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.results.append(
                ValidationResult(
                    test_name="Error Budget Calculation",
                    passed=False,
                    message=str(e),
                    duration_ms=duration_ms,
                )
            )
            print(f"  ✗ Budget calculation test failed: {e}")

    async def test_burn_rate_calculation(self):
        """Verify burn rate calculations for all windows."""
        print("\nTesting burn rate calculations...")

        start = time.time()
        try:
            response = requests.get(
                f"{API_URL}/api/v1/slo/status",
                timeout=5,
            )
            duration_ms = (time.time() - start) * 1000

            if response.status_code == 200:
                data = response.json()

                # Check burn rates for each SLI
                for sli_name in ["availability", "latency", "quality"]:
                    if sli_name not in data:
                        continue

                    sli_data = data[sli_name]

                    # Check burn rate windows
                    burn_rates = sli_data.get("burn_rates", {})

                    for window_hours, threshold in BURN_RATE_THRESHOLDS.items():
                        window_key = f"{window_hours}h"

                        if window_key not in burn_rates:
                            self.results.append(
                                ValidationResult(
                                    test_name=f"Burn Rate - {sli_name} ({window_key})",
                                    passed=False,
                                    message=f"Missing {window_key} window",
                                    duration_ms=duration_ms,
                                )
                            )
                            print(f"  ✗ {sli_name} {window_key}: Missing")
                            continue

                        burn_rate = burn_rates[window_key]["rate"]
                        is_critical = burn_rates[window_key]["is_critical"]

                        # Verify burn rate is non-negative
                        valid_rate = burn_rate >= 0

                        # Verify critical flag matches threshold
                        expected_critical = burn_rate > threshold
                        critical_correct = is_critical == expected_critical

                        passed = valid_rate and critical_correct

                        self.results.append(
                            ValidationResult(
                                test_name=f"Burn Rate - {sli_name} ({window_key})",
                                passed=passed,
                                message=f"Rate: {burn_rate:.2f} (threshold: {threshold}, critical: {is_critical})",
                                duration_ms=duration_ms,
                                details={
                                    "rate": burn_rate,
                                    "threshold": threshold,
                                    "is_critical": is_critical,
                                },
                            )
                        )

                        if passed:
                            status = "CRITICAL" if is_critical else "OK"
                            print(
                                f"  ✓ {sli_name} {window_key}: {burn_rate:.2f} ({status})"
                            )
                        else:
                            print(f"  ✗ {sli_name} {window_key}: Calculation error")

            else:
                self.results.append(
                    ValidationResult(
                        test_name="Burn Rate Calculation",
                        passed=False,
                        message=f"HTTP {response.status_code}",
                        duration_ms=duration_ms,
                    )
                )
                print(f"  ✗ Status API returned HTTP {response.status_code}")

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.results.append(
                ValidationResult(
                    test_name="Burn Rate Calculation",
                    passed=False,
                    message=str(e),
                    duration_ms=duration_ms,
                )
            )
            print(f"  ✗ Burn rate test failed: {e}")

    async def test_sli_recording(self):
        """Test that SLIs are being recorded correctly."""
        print("\nTesting SLI recording...")

        start = time.time()
        try:
            # Make a test request to generate SLI data
            requests.post(
                f"{API_URL}/api/v1/lint",
                json={"sql": "SELECT * FROM users"},
                timeout=5,
            )

            # Small delay to allow metrics to be recorded
            await asyncio.sleep(0.5)

            # Check SLO status
            response = requests.get(
                f"{API_URL}/api/v1/slo/status",
                timeout=5,
            )
            duration_ms = (time.time() - start) * 1000

            if response.status_code == 200:
                data = response.json()

                # Verify each SLI has current value
                for sli_name in ["availability", "latency", "quality"]:
                    if sli_name not in data:
                        self.results.append(
                            ValidationResult(
                                test_name=f"SLI Recording - {sli_name}",
                                passed=False,
                                message=f"SLI {sli_name} not found",
                                duration_ms=duration_ms,
                            )
                        )
                        print(f"  ✗ {sli_name}: Not found")
                        continue

                    sli_data = data[sli_name]

                    # Check for current value
                    if "current" not in sli_data:
                        self.results.append(
                            ValidationResult(
                                test_name=f"SLI Recording - {sli_name}",
                                passed=False,
                                message="Missing current value",
                                duration_ms=duration_ms,
                            )
                        )
                        print(f"  ✗ {sli_name}: Missing current value")
                        continue

                    current = sli_data["current"]
                    target = sli_data.get("target", 0)

                    # Verify value is in valid range [0, 1]
                    valid_range = 0 <= current <= 1

                    passed = valid_range

                    self.results.append(
                        ValidationResult(
                            test_name=f"SLI Recording - {sli_name}",
                            passed=passed,
                            message=f"Current: {current:.3f} (target: {target:.3f})",
                            duration_ms=duration_ms,
                            details={"current": current, "target": target},
                        )
                    )

                    if passed:
                        status = "✓" if current >= target else "⚠"
                        print(
                            f"  {status} {sli_name}: {current:.3f} (target: {target:.3f})"
                        )
                    else:
                        print(f"  ✗ {sli_name}: Invalid value {current}")

            else:
                self.results.append(
                    ValidationResult(
                        test_name="SLI Recording",
                        passed=False,
                        message=f"HTTP {response.status_code}",
                        duration_ms=duration_ms,
                    )
                )
                print(f"  ✗ Status API returned HTTP {response.status_code}")

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.results.append(
                ValidationResult(
                    test_name="SLI Recording",
                    passed=False,
                    message=str(e),
                    duration_ms=duration_ms,
                )
            )
            print(f"  ✗ SLI recording test failed: {e}")

    async def test_deployment_gating(self):
        """Test deployment gating based on error budget."""
        print("\nTesting deployment gating...")

        start = time.time()
        try:
            response = requests.get(
                f"{API_URL}/api/v1/slo/can-deploy",
                timeout=5,
            )
            duration_ms = (time.time() - start) * 1000

            if response.status_code == 200:
                data = response.json()

                # Check required fields
                required_fields = ["can_deploy", "reason", "budget_status"]
                has_all_fields = all(field in data for field in required_fields)

                if not has_all_fields:
                    self.results.append(
                        ValidationResult(
                            test_name="Deployment Gating",
                            passed=False,
                            message="Missing required fields",
                            duration_ms=duration_ms,
                        )
                    )
                    print("  ✗ Missing fields in can-deploy response")
                    return

                can_deploy = data["can_deploy"]
                reason = data["reason"]
                budget_status = data["budget_status"]

                # Verify boolean type
                passed = isinstance(can_deploy, bool)

                self.results.append(
                    ValidationResult(
                        test_name="Deployment Gating",
                        passed=passed,
                        message=f"Can deploy: {can_deploy} - {reason}",
                        duration_ms=duration_ms,
                        details={
                            "can_deploy": can_deploy,
                            "reason": reason,
                            "budget_status": budget_status,
                        },
                    )
                )

                if passed:
                    status = "✓ Yes" if can_deploy else "⚠ No"
                    print(f"  {status}: {reason}")
                else:
                    print("  ✗ Invalid can_deploy value")

            else:
                self.results.append(
                    ValidationResult(
                        test_name="Deployment Gating",
                        passed=False,
                        message=f"HTTP {response.status_code}",
                        duration_ms=duration_ms,
                    )
                )
                print(f"  ✗ Can-deploy API returned HTTP {response.status_code}")

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.results.append(
                ValidationResult(
                    test_name="Deployment Gating",
                    passed=False,
                    message=str(e),
                    duration_ms=duration_ms,
                )
            )
            print(f"  ✗ Deployment gating test failed: {e}")

    async def test_slo_report_generation(self):
        """Test SLO report generation."""
        print("\nTesting SLO report generation...")

        start = time.time()
        try:
            # Request report for last 7 days
            response = requests.get(
                f"{API_URL}/api/v1/slo/report",
                params={"days": 7},
                timeout=10,
            )
            duration_ms = (time.time() - start) * 1000

            if response.status_code == 200:
                data = response.json()

                # Check for required sections
                required_sections = ["summary", "slis", "incidents", "recommendations"]
                has_all_sections = all(section in data for section in required_sections)

                if not has_all_sections:
                    self.results.append(
                        ValidationResult(
                            test_name="SLO Report Generation",
                            passed=False,
                            message="Missing required sections",
                            duration_ms=duration_ms,
                        )
                    )
                    print("  ✗ Incomplete report structure")
                    return

                # Verify summary has key metrics
                summary = data["summary"]
                summary_fields = [
                    "period_days",
                    "overall_health",
                    "critical_burn_rates",
                ]
                has_summary_fields = all(field in summary for field in summary_fields)

                # Verify SLIs section has data for each SLI
                slis = data["slis"]
                has_sli_data = all(
                    sli in slis for sli in ["availability", "latency", "quality"]
                )

                passed = has_all_sections and has_summary_fields and has_sli_data

                self.results.append(
                    ValidationResult(
                        test_name="SLO Report Generation",
                        passed=passed,
                        message=f"Report generated for {summary.get('period_days', 0)} days",
                        duration_ms=duration_ms,
                        details={
                            "sections": list(data.keys()),
                            "overall_health": summary.get("overall_health", "unknown"),
                        },
                    )
                )

                if passed:
                    health = summary.get("overall_health", "unknown")
                    print(f"  ✓ Report generated: {health} health")
                else:
                    print("  ✗ Incomplete report structure")

            else:
                self.results.append(
                    ValidationResult(
                        test_name="SLO Report Generation",
                        passed=False,
                        message=f"HTTP {response.status_code}",
                        duration_ms=duration_ms,
                    )
                )
                print(f"  ✗ Report API returned HTTP {response.status_code}")

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.results.append(
                ValidationResult(
                    test_name="SLO Report Generation",
                    passed=False,
                    message=str(e),
                    duration_ms=duration_ms,
                )
            )
            print(f"  ✗ Report generation test failed: {e}")


async def main():
    """Run SLO tracking validation."""
    validator = SLOTrackingValidator()
    success, results = await validator.validate_all()

    # Save results
    import json

    with open("validation_results_slo.json", "w") as f:
        json.dump(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "success": success,
                "results": [
                    {
                        "test_name": r.test_name,
                        "passed": r.passed,
                        "message": r.message,
                        "duration_ms": r.duration_ms,
                        "details": r.details,
                    }
                    for r in results
                ],
            },
            f,
            indent=2,
        )

    print("\nResults saved to: validation_results_slo.json")

    return 0 if success else 1


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(main()))
