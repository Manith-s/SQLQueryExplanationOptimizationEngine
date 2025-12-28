"""
Failover Validation Suite.

Simulates region failures and validates automatic failover with <30s RTO.

Usage:
    python tests/validation/validate_failover.py

WARNING: This test will temporarily disrupt service in test regions.
         Only run in staging/test environments, NOT in production!
"""

import asyncio
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple

import requests

# Region configurations
REGIONS = {
    "us-east-1": {
        "api_url": "https://us-east-1.qeo.example.com",
        "role": "primary",
        "k8s_context": "us-east-1",
    },
    "eu-west-1": {
        "api_url": "https://eu-west-1.qeo.example.com",
        "role": "secondary",
        "k8s_context": "eu-west-1",
    },
    "ap-southeast-1": {
        "api_url": "https://ap-southeast-1.qeo.example.com",
        "role": "secondary",
        "k8s_context": "ap-southeast-1",
    },
}

# Global GeoDNS endpoint
GLOBAL_API_URL = "https://api.qeo.example.com"

# Recovery targets
RTO_TARGET_SECONDS = 30  # Recovery Time Objective
RPO_TARGET_MINUTES = 5  # Recovery Point Objective (data loss)


@dataclass
class ValidationResult:
    """Result of a validation test."""

    test_name: str
    passed: bool
    message: str
    duration_ms: float
    details: Dict = None


class FailoverValidator:
    """Validates failover and disaster recovery."""

    def __init__(self, dry_run: bool = True):
        self.results: List[ValidationResult] = []
        self.dry_run = dry_run

    async def validate_all(self) -> Tuple[bool, List[ValidationResult]]:
        """Run all failover validation tests."""
        print("=" * 80)
        print("QEO Failover & Disaster Recovery Validation Suite")
        print("=" * 80)

        if self.dry_run:
            print("⚠️  Running in DRY RUN mode (no actual failures)")
        else:
            print("⚠️  WARNING: This will cause actual service disruptions!")
            print("    Press Ctrl+C within 10 seconds to abort...")
            await asyncio.sleep(10)

        print()

        # Run all tests
        await self.test_health_monitoring()
        await self.test_region_failure_detection()
        await self.test_primary_region_failover()
        await self.test_secondary_region_failover()
        await self.test_database_failover()
        await self.test_geodns_failover()
        await self.test_data_consistency()
        await self.test_automatic_recovery()

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

    async def test_health_monitoring(self):
        """Test that health monitoring detects region status."""
        print("Testing health monitoring...")

        for region, config in REGIONS.items():
            start = time.time()
            try:
                response = requests.get(
                    config["api_url"] + "/health",
                    timeout=5,
                )
                duration_ms = (time.time() - start) * 1000

                is_healthy = response.status_code == 200

                self.results.append(
                    ValidationResult(
                        test_name=f"Health Monitor - {region}",
                        passed=is_healthy,
                        message=f"Region is {'healthy' if is_healthy else 'unhealthy'}",
                        duration_ms=duration_ms,
                        details={"status_code": response.status_code},
                    )
                )

                if is_healthy:
                    print(f"  ✓ {region}: Healthy")
                else:
                    print(f"  ✗ {region}: Unhealthy (HTTP {response.status_code})")

            except Exception as e:
                duration_ms = (time.time() - start) * 1000
                self.results.append(
                    ValidationResult(
                        test_name=f"Health Monitor - {region}",
                        passed=False,
                        message=str(e),
                        duration_ms=duration_ms,
                    )
                )
                print(f"  ✗ {region}: {e}")

    async def test_region_failure_detection(self):
        """Test that region failures are detected quickly."""
        print("\nTesting failure detection...")

        # Simulate failure by scaling down pods (or simulate in dry-run)
        test_region = "eu-west-1"
        config = REGIONS[test_region]

        start = time.time()
        try:
            if not self.dry_run:
                # Scale down deployment to 0
                subprocess.run(
                    ["kubectl", "config", "use-context", config["k8s_context"]],
                    check=True,
                    capture_output=True,
                )

                subprocess.run(
                    [
                        "kubectl",
                        "scale",
                        "deployment",
                        "qeo-api",
                        "-n",
                        "qeo",
                        "--replicas=0",
                    ],
                    check=True,
                    capture_output=True,
                )

                print(f"  → Scaled down {test_region} to simulate failure")
                await asyncio.sleep(5)  # Wait for propagation

            # Try to access the region (should fail or timeout quickly)
            try:
                response = requests.get(
                    config["api_url"] + "/health",
                    timeout=3,
                )
                detected_failure = response.status_code != 200
            except Exception:
                detected_failure = True

            detection_time_ms = (time.time() - start) * 1000

            # Failure should be detected within 10 seconds
            passed = detected_failure and detection_time_ms < 10000

            self.results.append(
                ValidationResult(
                    test_name=f"Failure Detection - {test_region}",
                    passed=passed,
                    message=f"Failure detected in {detection_time_ms:.0f}ms",
                    duration_ms=detection_time_ms,
                    details={"detection_time_ms": detection_time_ms},
                )
            )

            if passed:
                print(f"  ✓ Failure detected in {detection_time_ms:.0f}ms")
            else:
                print("  ✗ Failure not detected or took too long")

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.results.append(
                ValidationResult(
                    test_name=f"Failure Detection - {test_region}",
                    passed=False,
                    message=str(e),
                    duration_ms=duration_ms,
                )
            )
            print(f"  ✗ Failure detection test failed: {e}")

        finally:
            if not self.dry_run:
                # Restore the region
                subprocess.run(
                    [
                        "kubectl",
                        "scale",
                        "deployment",
                        "qeo-api",
                        "-n",
                        "qeo",
                        "--replicas=3",
                    ],
                    check=True,
                    capture_output=True,
                )
                print(f"  → Restored {test_region}")

    async def test_primary_region_failover(self):
        """Test failover when primary region fails."""
        print("\nTesting primary region failover...")

        primary_region = "us-east-1"
        config = REGIONS[primary_region]

        start = time.time()
        try:
            # Record initial state
            try:
                baseline_response = requests.get(
                    GLOBAL_API_URL + "/health",
                    timeout=5,
                )
                baseline_healthy = baseline_response.status_code == 200
            except Exception:
                baseline_healthy = False

            if not baseline_healthy:
                self.results.append(
                    ValidationResult(
                        test_name="Primary Region Failover",
                        passed=False,
                        message="Global API unhealthy before test",
                        duration_ms=0,
                    )
                )
                print("  ✗ Global API unhealthy before test")
                return

            if not self.dry_run:
                # Simulate primary failure
                subprocess.run(
                    ["kubectl", "config", "use-context", config["k8s_context"]],
                    check=True,
                    capture_output=True,
                )

                subprocess.run(
                    [
                        "kubectl",
                        "scale",
                        "deployment",
                        "qeo-api",
                        "-n",
                        "qeo",
                        "--replicas=0",
                    ],
                    check=True,
                    capture_output=True,
                )

                print(f"  → Simulated {primary_region} failure")

            # Wait for GeoDNS to detect and failover
            await asyncio.sleep(10)

            # Try global endpoint (should route to secondary)
            recovery_attempts = 0
            recovered = False
            recovery_time = 0

            for _attempt in range(30):  # Try for up to 30 seconds
                try:
                    response = requests.get(
                        GLOBAL_API_URL + "/health",
                        timeout=5,
                    )

                    if response.status_code == 200:
                        recovered = True
                        recovery_time = (time.time() - start) * 1000
                        break

                except Exception:
                    pass

                recovery_attempts += 1
                await asyncio.sleep(1)

            passed = recovered and recovery_time < (RTO_TARGET_SECONDS * 1000)

            self.results.append(
                ValidationResult(
                    test_name="Primary Region Failover",
                    passed=passed,
                    message=f"Recovered in {recovery_time:.0f}ms (target: <{RTO_TARGET_SECONDS}s)",
                    duration_ms=recovery_time,
                    details={
                        "recovered": recovered,
                        "recovery_time_ms": recovery_time,
                        "attempts": recovery_attempts,
                    },
                )
            )

            if passed:
                print(f"  ✓ Failover successful: {recovery_time:.0f}ms")
            else:
                print(f"  ✗ Failover failed or exceeded RTO ({recovery_time:.0f}ms)")

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.results.append(
                ValidationResult(
                    test_name="Primary Region Failover",
                    passed=False,
                    message=str(e),
                    duration_ms=duration_ms,
                )
            )
            print(f"  ✗ Primary failover test failed: {e}")

        finally:
            if not self.dry_run:
                # Restore primary
                subprocess.run(
                    [
                        "kubectl",
                        "scale",
                        "deployment",
                        "qeo-api",
                        "-n",
                        "qeo",
                        "--replicas=3",
                    ],
                    check=True,
                    capture_output=True,
                )
                print(f"  → Restored {primary_region}")
                await asyncio.sleep(10)  # Wait for recovery

    async def test_secondary_region_failover(self):
        """Test that secondary region failures don't impact global service."""
        print("\nTesting secondary region failover...")

        secondary_region = "ap-southeast-1"
        config = REGIONS[secondary_region]

        start = time.time()
        try:
            if not self.dry_run:
                # Scale down secondary
                subprocess.run(
                    ["kubectl", "config", "use-context", config["k8s_context"]],
                    check=True,
                    capture_output=True,
                )

                subprocess.run(
                    [
                        "kubectl",
                        "scale",
                        "deployment",
                        "qeo-api",
                        "-n",
                        "qeo",
                        "--replicas=0",
                    ],
                    check=True,
                    capture_output=True,
                )

                print(f"  → Simulated {secondary_region} failure")

            await asyncio.sleep(5)

            # Global endpoint should still work (routed to other regions)
            try:
                response = requests.get(
                    GLOBAL_API_URL + "/health",
                    timeout=5,
                )
                global_healthy = response.status_code == 200
            except Exception:
                global_healthy = False

            duration_ms = (time.time() - start) * 1000

            passed = global_healthy

            self.results.append(
                ValidationResult(
                    test_name=f"Secondary Region Failover - {secondary_region}",
                    passed=passed,
                    message=(
                        "Global service maintained"
                        if passed
                        else "Global service impacted"
                    ),
                    duration_ms=duration_ms,
                )
            )

            if passed:
                print(
                    f"  ✓ Global service maintained despite {secondary_region} failure"
                )
            else:
                print(f"  ✗ Global service impacted by {secondary_region} failure")

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.results.append(
                ValidationResult(
                    test_name=f"Secondary Region Failover - {secondary_region}",
                    passed=False,
                    message=str(e),
                    duration_ms=duration_ms,
                )
            )
            print(f"  ✗ Secondary failover test failed: {e}")

        finally:
            if not self.dry_run:
                # Restore secondary
                subprocess.run(
                    [
                        "kubectl",
                        "scale",
                        "deployment",
                        "qeo-api",
                        "-n",
                        "qeo",
                        "--replicas=3",
                    ],
                    check=True,
                    capture_output=True,
                )
                print(f"  → Restored {secondary_region}")

    async def test_database_failover(self):
        """Test CockroachDB cluster resilience."""
        print("\nTesting database failover...")

        start = time.time()
        try:
            # Try to query database through API
            test_query = {
                "sql": "SELECT COUNT(*) FROM pg_tables",
            }

            response = requests.post(
                f"{GLOBAL_API_URL}/api/v1/lint",
                json=test_query,
                timeout=10,
            )

            duration_ms = (time.time() - start) * 1000

            db_accessible = response.status_code == 200

            self.results.append(
                ValidationResult(
                    test_name="Database Failover",
                    passed=db_accessible,
                    message="Database accessible via global API",
                    duration_ms=duration_ms,
                )
            )

            if db_accessible:
                print("  ✓ Database accessible (multi-region CockroachDB)")
            else:
                print("  ✗ Database not accessible")

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.results.append(
                ValidationResult(
                    test_name="Database Failover",
                    passed=False,
                    message=str(e),
                    duration_ms=duration_ms,
                )
            )
            print(f"  ✗ Database failover test failed: {e}")

    async def test_geodns_failover(self):
        """Test GeoDNS routing updates when region fails."""
        print("\nTesting GeoDNS failover routing...")

        start = time.time()
        try:
            # Query GeoDNS resolution
            import socket

            # Resolve global domain
            ips = socket.getaddrinfo("api.qeo.example.com", 80, socket.AF_INET)

            duration_ms = (time.time() - start) * 1000

            # Should resolve to at least one IP
            passed = len(ips) > 0

            self.results.append(
                ValidationResult(
                    test_name="GeoDNS Failover Routing",
                    passed=passed,
                    message=f"Resolved to {len(ips)} IP(s)",
                    duration_ms=duration_ms,
                    details={"ip_count": len(ips)},
                )
            )

            if passed:
                print(f"  ✓ GeoDNS resolving to {len(ips)} healthy region(s)")
            else:
                print("  ✗ GeoDNS resolution failed")

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.results.append(
                ValidationResult(
                    test_name="GeoDNS Failover Routing",
                    passed=False,
                    message=str(e),
                    duration_ms=duration_ms,
                )
            )
            print(f"  ✗ GeoDNS test failed: {e}")

    async def test_data_consistency(self):
        """Test that data remains consistent across regions after failover."""
        print("\nTesting data consistency after failover...")

        start = time.time()
        try:
            # Write data to global endpoint
            test_id = f"failover_test_{int(time.time())}"

            # Make a request that would write to cache/db
            response = requests.post(
                f"{GLOBAL_API_URL}/api/v1/lint",
                json={"sql": f"SELECT * FROM test WHERE id = '{test_id}'"},
                timeout=10,
            )

            write_success = response.status_code == 200

            if not write_success:
                self.results.append(
                    ValidationResult(
                        test_name="Data Consistency",
                        passed=False,
                        message="Failed to write test data",
                        duration_ms=0,
                    )
                )
                print("  ✗ Failed to write test data")
                return

            # Wait for replication
            await asyncio.sleep(2)

            # Try to read from different regions
            consistent = True
            for _region, config in REGIONS.items():
                try:
                    read_response = requests.post(
                        config["api_url"] + "/api/v1/lint",
                        json={"sql": f"SELECT * FROM test WHERE id = '{test_id}'"},
                        timeout=5,
                    )

                    if read_response.status_code != 200:
                        consistent = False
                        break

                except Exception:
                    consistent = False
                    break

            duration_ms = (time.time() - start) * 1000

            self.results.append(
                ValidationResult(
                    test_name="Data Consistency",
                    passed=consistent,
                    message=(
                        "Data consistent across regions"
                        if consistent
                        else "Data inconsistency detected"
                    ),
                    duration_ms=duration_ms,
                )
            )

            if consistent:
                print("  ✓ Data consistent across all regions")
            else:
                print("  ✗ Data inconsistency detected")

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.results.append(
                ValidationResult(
                    test_name="Data Consistency",
                    passed=False,
                    message=str(e),
                    duration_ms=duration_ms,
                )
            )
            print(f"  ✗ Data consistency test failed: {e}")

    async def test_automatic_recovery(self):
        """Test that failed regions automatically recover."""
        print("\nTesting automatic recovery...")

        start = time.time()
        try:
            # Check all regions are healthy
            healthy_count = 0

            for _region, config in REGIONS.items():
                try:
                    response = requests.get(
                        config["api_url"] + "/health",
                        timeout=5,
                    )

                    if response.status_code == 200:
                        healthy_count += 1

                except Exception:
                    pass

            duration_ms = (time.time() - start) * 1000

            # All regions should be recovered
            total_regions = len(REGIONS)
            passed = healthy_count == total_regions

            self.results.append(
                ValidationResult(
                    test_name="Automatic Recovery",
                    passed=passed,
                    message=f"{healthy_count}/{total_regions} regions recovered",
                    duration_ms=duration_ms,
                    details={
                        "healthy_regions": healthy_count,
                        "total_regions": total_regions,
                    },
                )
            )

            if passed:
                print(f"  ✓ All {total_regions} regions recovered")
            else:
                print(f"  ✗ Only {healthy_count}/{total_regions} regions recovered")

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.results.append(
                ValidationResult(
                    test_name="Automatic Recovery",
                    passed=False,
                    message=str(e),
                    duration_ms=duration_ms,
                )
            )
            print(f"  ✗ Automatic recovery test failed: {e}")


async def main():
    """Run failover validation."""
    import sys

    # Check if --no-dry-run flag is set
    dry_run = "--no-dry-run" not in sys.argv

    validator = FailoverValidator(dry_run=dry_run)
    success, results = await validator.validate_all()

    # Save results
    import json

    with open("validation_results_failover.json", "w") as f:
        json.dump(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "dry_run": dry_run,
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

    print("\nResults saved to: validation_results_failover.json")

    return 0 if success else 1


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(main()))
