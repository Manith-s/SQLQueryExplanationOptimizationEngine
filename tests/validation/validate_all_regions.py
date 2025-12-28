"""
Multi-Region Validation Suite.

Tests connectivity to all 3 regions and verifies CockroachDB replication.

Usage:
    python tests/validation/validate_all_regions.py
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple

import psycopg2
import requests

# Region configurations
REGIONS = {
    "us-east-1": {
        "api_url": "https://us-east-1.qeo.example.com",
        "db_host": "cockroachdb-us-east-1.qeo.svc.cluster.local",
        "db_port": 26257,
        "expected_role": "primary",
    },
    "eu-west-1": {
        "api_url": "https://eu-west-1.qeo.example.com",
        "db_host": "cockroachdb-eu-west-1.qeo.svc.cluster.local",
        "db_port": 26257,
        "expected_role": "secondary",
    },
    "ap-southeast-1": {
        "api_url": "https://ap-southeast-1.qeo.example.com",
        "db_host": "cockroachdb-ap-southeast-1.qeo.svc.cluster.local",
        "db_port": 26257,
        "expected_role": "secondary",
    },
}


@dataclass
class ValidationResult:
    """Result of a validation test."""
    test_name: str
    passed: bool
    message: str
    duration_ms: float
    details: Dict = None


class RegionValidator:
    """Validates multi-region deployment."""

    def __init__(self):
        self.results: List[ValidationResult] = []

    async def validate_all(self) -> Tuple[bool, List[ValidationResult]]:
        """Run all validation tests."""
        print("=" * 80)
        print("QEO Multi-Region Validation Suite")
        print("=" * 80)
        print()

        # Run all tests
        await self.test_region_connectivity()
        await self.test_api_health()
        await self.test_cockroachdb_replication()
        await self.test_cross_region_latency()
        await self.test_data_residency()
        await self.test_failover_readiness()

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

    async def test_region_connectivity(self):
        """Test network connectivity to all regions."""
        print("Testing region connectivity...")

        for region, config in REGIONS.items():
            start = time.time()
            try:
                response = requests.get(
                    config["api_url"] + "/health",
                    timeout=10,
                )
                duration_ms = (time.time() - start) * 1000

                if response.status_code == 200:
                    self.results.append(ValidationResult(
                        test_name=f"Region Connectivity - {region}",
                        passed=True,
                        message=f"Successfully connected to {region}",
                        duration_ms=duration_ms,
                        details={"status_code": 200, "response_time_ms": duration_ms}
                    ))
                    print(f"  ✓ {region}: Connected ({duration_ms:.0f}ms)")
                else:
                    self.results.append(ValidationResult(
                        test_name=f"Region Connectivity - {region}",
                        passed=False,
                        message=f"HTTP {response.status_code}",
                        duration_ms=duration_ms,
                    ))
                    print(f"  ✗ {region}: HTTP {response.status_code}")

            except Exception as e:
                duration_ms = (time.time() - start) * 1000
                self.results.append(ValidationResult(
                    test_name=f"Region Connectivity - {region}",
                    passed=False,
                    message=str(e),
                    duration_ms=duration_ms,
                ))
                print(f"  ✗ {region}: {e}")

    async def test_api_health(self):
        """Test API health endpoints in all regions."""
        print("\nTesting API health endpoints...")

        for region, config in REGIONS.items():
            start = time.time()
            try:
                response = requests.get(
                    config["api_url"] + "/health",
                    timeout=5,
                )
                duration_ms = (time.time() - start) * 1000

                if response.status_code == 200:
                    data = response.json()
                    passed = data.get("status") == "healthy"

                    self.results.append(ValidationResult(
                        test_name=f"API Health - {region}",
                        passed=passed,
                        message=f"API is {data.get('status', 'unknown')}",
                        duration_ms=duration_ms,
                        details=data,
                    ))

                    if passed:
                        print(f"  ✓ {region}: Healthy")
                    else:
                        print(f"  ✗ {region}: {data.get('status')}")
                else:
                    self.results.append(ValidationResult(
                        test_name=f"API Health - {region}",
                        passed=False,
                        message=f"HTTP {response.status_code}",
                        duration_ms=duration_ms,
                    ))
                    print(f"  ✗ {region}: HTTP {response.status_code}")

            except Exception as e:
                duration_ms = (time.time() - start) * 1000
                self.results.append(ValidationResult(
                    test_name=f"API Health - {region}",
                    passed=False,
                    message=str(e),
                    duration_ms=duration_ms,
                ))
                print(f"  ✗ {region}: {e}")

    async def test_cockroachdb_replication(self):
        """Test CockroachDB replication across regions."""
        print("\nTesting CockroachDB replication...")

        # Test data
        test_id = f"test_{int(time.time())}"
        test_value = f"validation_{datetime.utcnow().isoformat()}"

        start = time.time()
        try:
            # Write to primary region
            primary_config = REGIONS["us-east-1"]
            conn = psycopg2.connect(
                host=primary_config["db_host"],
                port=primary_config["db_port"],
                user="root",
                database="queryexpnopt",
                sslmode="require",
                connect_timeout=10,
            )

            cursor = conn.cursor()

            # Create test table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS validation_test (
                    id TEXT PRIMARY KEY,
                    value TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)

            # Insert test data
            cursor.execute(
                "INSERT INTO validation_test (id, value) VALUES (%s, %s)",
                (test_id, test_value)
            )
            conn.commit()

            write_duration = (time.time() - start) * 1000
            print(f"  ✓ Write to primary: {write_duration:.0f}ms")

            # Wait for replication (CockroachDB is typically <100ms)
            await asyncio.sleep(1)

            # Read from secondary regions
            for region in ["eu-west-1", "ap-southeast-1"]:
                read_start = time.time()
                config = REGIONS[region]

                try:
                    read_conn = psycopg2.connect(
                        host=config["db_host"],
                        port=config["db_port"],
                        user="root",
                        database="queryexpnopt",
                        sslmode="require",
                        connect_timeout=10,
                    )

                    read_cursor = read_conn.cursor()
                    read_cursor.execute(
                        "SELECT value FROM validation_test WHERE id = %s",
                        (test_id,)
                    )
                    result = read_cursor.fetchone()

                    read_duration = (time.time() - read_start) * 1000

                    if result and result[0] == test_value:
                        self.results.append(ValidationResult(
                            test_name=f"CockroachDB Replication - {region}",
                            passed=True,
                            message="Data replicated successfully",
                            duration_ms=read_duration,
                            details={"replication_lag_ms": read_duration - write_duration}
                        ))
                        print(f"  ✓ {region}: Replicated ({read_duration:.0f}ms)")
                    else:
                        self.results.append(ValidationResult(
                            test_name=f"CockroachDB Replication - {region}",
                            passed=False,
                            message="Data not found or mismatch",
                            duration_ms=read_duration,
                        ))
                        print(f"  ✗ {region}: Replication failed")

                    read_conn.close()

                except Exception as e:
                    read_duration = (time.time() - read_start) * 1000
                    self.results.append(ValidationResult(
                        test_name=f"CockroachDB Replication - {region}",
                        passed=False,
                        message=str(e),
                        duration_ms=read_duration,
                    ))
                    print(f"  ✗ {region}: {e}")

            # Cleanup
            cursor.execute("DELETE FROM validation_test WHERE id = %s", (test_id,))
            conn.commit()
            conn.close()

        except Exception as e:
            duration = (time.time() - start) * 1000
            self.results.append(ValidationResult(
                test_name="CockroachDB Replication - Write",
                passed=False,
                message=str(e),
                duration_ms=duration,
            ))
            print(f"  ✗ Primary write failed: {e}")

    async def test_cross_region_latency(self):
        """Test latency between regions."""
        print("\nTesting cross-region latency...")

        latencies = {}

        for region, config in REGIONS.items():
            start = time.time()
            try:
                requests.get(
                    config["api_url"] + "/health",
                    timeout=5,
                )
                latency_ms = (time.time() - start) * 1000
                latencies[region] = latency_ms

                # Expected latencies (rough estimates)
                expected_max = {
                    "us-east-1": 100,  # Within US
                    "eu-west-1": 200,  # Trans-Atlantic
                    "ap-southeast-1": 300,  # Trans-Pacific
                }

                passed = latency_ms < expected_max[region]

                self.results.append(ValidationResult(
                    test_name=f"Cross-Region Latency - {region}",
                    passed=passed,
                    message=f"Latency: {latency_ms:.0f}ms (max: {expected_max[region]}ms)",
                    duration_ms=latency_ms,
                ))

                if passed:
                    print(f"  ✓ {region}: {latency_ms:.0f}ms")
                else:
                    print(f"  ✗ {region}: {latency_ms:.0f}ms (exceeded threshold)")

            except Exception as e:
                self.results.append(ValidationResult(
                    test_name=f"Cross-Region Latency - {region}",
                    passed=False,
                    message=str(e),
                    duration_ms=0,
                ))
                print(f"  ✗ {region}: {e}")

    async def test_data_residency(self):
        """Test GDPR-compliant data residency enforcement."""
        print("\nTesting data residency enforcement...")

        start = time.time()
        try:
            # Test that EU requests route to EU region
            response = requests.post(
                "https://api.qeo.example.com/api/v1/optimize",
                json={
                    "sql": "SELECT * FROM users WHERE country = 'DE'",
                    "user_country": "DE",
                    "requires_eu_residency": True,
                },
                headers={"X-User-Country": "DE"},
                timeout=10,
            )

            duration_ms = (time.time() - start) * 1000

            # Check X-Region header to verify routing
            routed_region = response.headers.get("X-Region", "unknown")

            if routed_region == "eu-west-1":
                self.results.append(ValidationResult(
                    test_name="Data Residency - GDPR Enforcement",
                    passed=True,
                    message=f"EU request correctly routed to {routed_region}",
                    duration_ms=duration_ms,
                ))
                print("  ✓ GDPR: EU data stayed in EU region")
            else:
                self.results.append(ValidationResult(
                    test_name="Data Residency - GDPR Enforcement",
                    passed=False,
                    message=f"EU request routed to {routed_region} instead of eu-west-1",
                    duration_ms=duration_ms,
                ))
                print(f"  ✗ GDPR: Routed to {routed_region} (expected eu-west-1)")

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.results.append(ValidationResult(
                test_name="Data Residency - GDPR Enforcement",
                passed=False,
                message=str(e),
                duration_ms=duration_ms,
            ))
            print(f"  ✗ GDPR test failed: {e}")

    async def test_failover_readiness(self):
        """Test that failover mechanisms are ready."""
        print("\nTesting failover readiness...")

        start = time.time()
        try:
            # Check health of backup regions
            backup_regions = ["eu-west-1", "ap-southeast-1"]
            healthy_backups = 0

            for region in backup_regions:
                config = REGIONS[region]
                response = requests.get(
                    config["api_url"] + "/health",
                    timeout=5,
                )

                if response.status_code == 200:
                    healthy_backups += 1

            duration_ms = (time.time() - start) * 1000

            passed = healthy_backups >= 1  # Need at least 1 backup

            self.results.append(ValidationResult(
                test_name="Failover Readiness",
                passed=passed,
                message=f"{healthy_backups}/{len(backup_regions)} backup regions healthy",
                duration_ms=duration_ms,
                details={"healthy_backups": healthy_backups}
            ))

            if passed:
                print(f"  ✓ Failover ready: {healthy_backups} backup regions available")
            else:
                print(f"  ✗ Insufficient backup regions: {healthy_backups}")

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.results.append(ValidationResult(
                test_name="Failover Readiness",
                passed=False,
                message=str(e),
                duration_ms=duration_ms,
            ))
            print(f"  ✗ Failover test failed: {e}")


async def main():
    """Run validation suite."""
    validator = RegionValidator()
    success, results = await validator.validate_all()

    # Save results
    import json
    with open("validation_results_regions.json", "w") as f:
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
                ]
            },
            f,
            indent=2,
        )

    print("\nResults saved to: validation_results_regions.json")

    return 0 if success else 1


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))
